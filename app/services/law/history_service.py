"""Resumable historical archive. Never mutates law_articles or live embeddings."""
import asyncio
from contextlib import asynccontextmanager
import difflib
import re

import httpx

from app.database import get_pool
from app.services.law.history_parser import listing, parse, redact, sha, PARSER_VERSION
from config import LAW_API_KEY

BASE = 'https://www.law.go.kr/DRF/'
LOCK_ID = 2026092203


class HistoryAPI:
    def __init__(self):
        if not LAW_API_KEY:
            raise ValueError('LAW_API_KEY missing')
        self.client = httpx.AsyncClient(timeout=45, follow_redirects=False)

    async def get(self, endpoint, **params):
        for attempt in range(3):
            await asyncio.sleep(0.5 if attempt == 0 else 2 ** attempt)
            try:
                response = await self.client.get(BASE + endpoint,
                    params=dict(OC=LAW_API_KEY, type='XML', **params))
                response.raise_for_status()
                return redact(response.text, LAW_API_KEY)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise RuntimeError('HistoryNetworkError') from None
            except httpx.HTTPStatusError as exc:
                if attempt == 2 or exc.response.status_code not in (429,500,502,503,504):
                    raise RuntimeError('HistoryHTTPError') from None

    async def close(self):
        await self.client.aclose()


@asynccontextmanager
async def worker(phase):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not await conn.fetchval('SELECT pg_try_advisory_lock($1)', LOCK_ID):
            raise RuntimeError('HistoryWorkerAlreadyRunning')
        run_id = None
        try:
            await conn.execute("UPDATE law_history.runs SET status='interrupted',finished_at=now() WHERE status='running'")
            run_id = await conn.fetchval('INSERT INTO law_history.runs(phase) VALUES($1) RETURNING id', phase)
            yield conn, run_id
        except BaseException as exc:
            if run_id:
                await conn.execute("UPDATE law_history.runs SET status='interrupted',error_type=$2,finished_at=now() WHERE id=$1",run_id,type(exc).__name__)
            raise
        finally:
            await conn.execute('SELECT pg_advisory_unlock($1)', LOCK_ID)


async def freeze_scope(conn):
    if await conn.fetchval('SELECT count(*) FROM law_history.scope'):
        return
    # Snapshot only already-collected official statutes, not interpretation topics.
    rows = await conn.fetch("""SELECT law_name,min(source_url) source FROM law_articles
        WHERE is_current AND source_url LIKE '%lsiSeq=%' GROUP BY law_name ORDER BY law_name""")
    if not rows:
        raise ValueError('No current official statutes found')
    values = []
    for row in rows:
        match = re.search(r'[?&]lsiSeq=(\d+)', row['source'])
        if not match:
            raise ValueError('Invalid source MST')
        values.append((row['law_name'], match[1]))
    async with conn.transaction():
        await conn.executemany('INSERT INTO law_history.scope(law_name,seed_mst) VALUES($1,$2)', values)


async def discover(refresh=False):
    api = HistoryAPI()
    try:
        async with worker('discover') as (conn, run_id):
            await freeze_scope(conn)
            targets = await conn.fetch("SELECT * FROM law_history.scope WHERE discovery_status<>'complete' OR $1 ORDER BY id",refresh)
            for target in targets:
                try:
                    await conn.execute("UPDATE law_history.scope SET discovery_status='pending' WHERE id=$1",target['id'])
                    seed = parse(await api.get('lawService.do',target='law',MST=target['seed_mst']))
                    lid = seed['law_id']
                    await conn.execute('INSERT INTO law_history.laws(law_id,seed_name) VALUES($1,$2) ON CONFLICT DO NOTHING',lid,target['law_name'])
                    await conn.execute('UPDATE law_history.scope SET law_id=$2 WHERE id=$1',target['id'],lid)
                    seen, expected = set(), None
                    for page in range(1,1001):
                        xml = await api.get('lawSearch.do',target='eflaw',LID=lid,nw='1,2,3',display=100,page=page,sort='ddes')
                        rows,total = listing(xml,lid)
                        if expected is not None and expected != total:
                            raise ValueError('Listing changed during pagination')
                        expected = total
                        if not rows:
                            raise ValueError('Empty or incomplete history listing')
                        before = len(seen)
                        for row in rows:
                            key = (row['mst'],row['effective_date'])
                            if key in seen:
                                raise ValueError('Duplicate history page or version')
                            seen.add(key)
                        async with conn.transaction():
                            for row in rows:
                                await conn.execute('''INSERT INTO law_history.versions
                                    (law_id,mst,effective_date,law_name,law_type,promulgation_date,
                                     promulgation_number,revision_type,listing_status,listing_metadata)
                                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                                    ON CONFLICT(law_id,mst,effective_date) DO NOTHING''',
                                    lid,row['mst'],row['effective_date'],row['law_name'],row['law_type'],
                                    row['promulgation_date'],row['promulgation_number'],row['revision_type'],
                                    row['listing_status'],row['metadata'])
                        await conn.execute('UPDATE law_history.scope SET expected_count=$2 WHERE id=$1',target['id'],expected)
                        await conn.execute('UPDATE law_history.runs SET heartbeat_at=now() WHERE id=$1',run_id)
                        if len(seen) == expected:
                            break
                        if len(seen) > expected or len(seen) == before:
                            raise ValueError('Invalid history pagination count')
                    else:
                        raise ValueError('History pagination safety limit')
                    await conn.execute("UPDATE law_history.scope SET discovery_status='complete',error_type=NULL,discovered_at=now() WHERE id=$1",target['id'])
                    await conn.execute('UPDATE law_history.runs SET completed=completed+1 WHERE id=$1',run_id)
                    print(f'DISCOVERED {target["law_name"]}: {len(seen)}',flush=True)
                except Exception as exc:
                    await conn.execute("UPDATE law_history.scope SET discovery_status='failed',error_type=$2 WHERE id=$1",target['id'],type(exc).__name__)
                    await conn.execute('UPDATE law_history.runs SET failed=failed+1 WHERE id=$1',run_id)
                    print(f'DISCOVERY FAILED scope={target["id"]} {type(exc).__name__}',flush=True)
            await finish(conn,run_id)
    finally:
        await api.close()


async def finish(conn, run_id):
    await conn.execute("UPDATE law_history.runs SET status=CASE WHEN failed=0 THEN 'complete' ELSE 'partial' END,finished_at=now(),heartbeat_at=now() WHERE id=$1",run_id)


async def store(conn, version, xml):
    parsed = parse(xml,law_id=version['law_id'],effective_date=version['effective_date'],promulgation_date=version['promulgation_date'])
    source = f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={version["mst"]}&efYd={version["effective_date"]:%Y%m%d}'
    async with conn.transaction():
        snapshot = await conn.fetchval('''INSERT INTO law_history.snapshots
            (version_id,content_hash,raw_xml,source_url,parser_version) VALUES($1,$2,$3,$4,$5)
            ON CONFLICT DO NOTHING RETURNING id''',version['id'],sha(xml),xml,source,PARSER_VERSION)
        if snapshot:
            await conn.executemany('''INSERT INTO law_history.articles
                (snapshot_id,source_order,source_key,article_number,article_branch,unit_kind,title,body,content_hash,structure)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''',
                [(snapshot,a['source_order'],a['source_key'],a['article_number'],a['article_branch'],a['unit_kind'],a['title'],a['body'],a['content_hash'],a['structure']) for a in parsed['articles']])
            await conn.executemany('''INSERT INTO law_history.supplements
                (snapshot_id,source_order,source_key,body,structure) VALUES($1,$2,$3,$4,$5)''',
                [(snapshot,a['source_order'],a['source_key'],a['body'],a['structure']) for a in parsed['supplements']])
        await conn.execute("UPDATE law_history.versions SET fetch_status='complete',error_type=NULL WHERE id=$1",version['id'])


async def collect(limit=None, retry_failed=False, refresh=False, version_id=None):
    api = HistoryAPI()
    try:
        async with worker('collect') as (conn,run_id):
            # Freeze this pass, so permanent failures are never retried in a tight loop.
            rows = await conn.fetch('''SELECT v.* FROM law_history.versions v
                WHERE (v.fetch_status='pending' OR ($1 AND v.fetch_status='failed') OR $3)
                  AND ($4::bigint IS NULL OR v.id=$4)
                ORDER BY (effective_date>current_date),effective_date DESC,id LIMIT $2''',retry_failed,limit,refresh,version_id)
            consecutive_failures = 0
            for version in rows:
                await conn.execute('UPDATE law_history.versions SET attempts=attempts+1,last_attempt_at=now() WHERE id=$1',version['id'])
                try:
                    xml = await api.get('lawService.do',target='eflaw',MST=version['mst'],efYd=version['effective_date'].strftime('%Y%m%d'))
                    await store(conn,version,xml)
                    consecutive_failures = 0
                    await conn.execute('UPDATE law_history.runs SET completed=completed+1,heartbeat_at=now() WHERE id=$1',run_id)
                    print(f'STORED version={version["id"]} {version["law_name"]} {version["effective_date"]}',flush=True)
                except Exception as exc:
                    await conn.execute("UPDATE law_history.versions SET fetch_status='failed',error_type=$2 WHERE id=$1",version['id'],type(exc).__name__)
                    await conn.execute('UPDATE law_history.runs SET failed=failed+1,heartbeat_at=now() WHERE id=$1',run_id)
                    print(f'FETCH FAILED version={version["id"]} {type(exc).__name__}',flush=True)
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        print('STOPPED: five consecutive failures; inspect before retry',flush=True)
                        break
            await finish(conn,run_id)
    finally:
        await api.close()


def observed_run_status(run, lock_held, heartbeat_age):
    """Observation only: never mark an unresponsive owner safe to replace."""
    if run['status'] != 'running':
        return run['status']
    if not lock_held:
        return 'interrupted'
    return 'unresponsive' if heartbeat_age > 180 else 'running'


async def status():
    pool = await get_pool()
    lock_held = await pool.fetchval('''SELECT EXISTS(SELECT 1 FROM pg_locks
        WHERE locktype='advisory' AND classid=0 AND objid=$1 AND objsubid=1
        AND granted AND database=(SELECT oid FROM pg_database WHERE datname=current_database()))''', LOCK_ID)
    runs = [dict(r) for r in await pool.fetch('''SELECT *,
        extract(epoch FROM now()-heartbeat_at)::float8 AS heartbeat_age_seconds
        FROM law_history.runs ORDER BY id DESC LIMIT 5''')]
    for run in runs:
        run['observed_status'] = observed_run_status(run, lock_held, run['heartbeat_age_seconds'])
    return dict(coverage=[dict(r) for r in await pool.fetch('SELECT * FROM law_history.coverage ORDER BY id')],
        worker_lock_held=lock_held, runs=runs,
        snapshots=await pool.fetchval('SELECT count(*) FROM law_history.snapshots'),
        articles=await pool.fetchval('SELECT count(*) FROM law_history.articles'),
        supplements=await pool.fetchval('SELECT count(*) FROM law_history.supplements'))


async def versions(law_id):
    pool = await get_pool()
    return [dict(r) for r in await pool.fetch('''SELECT v.id,v.law_id,v.mst,v.law_name,v.effective_date,
        v.promulgation_date,v.revision_type,v.fetch_status,s.previous_observed_version_id
        FROM law_history.versions v JOIN law_history.version_sequence s USING(id)
        WHERE v.law_id=$1 ORDER BY v.effective_date,v.promulgation_date,v.mst''',law_id)]


async def show(version_id):
    pool = await get_pool()
    version = await pool.fetchrow('SELECT * FROM law_history.versions WHERE id=$1',version_id)
    if not version:
        raise ValueError('Unknown version')
    snapshot = await pool.fetchrow('''SELECT id,version_id,content_hash,source_url,collected_at,parser_version
        FROM law_history.snapshots WHERE version_id=$1 ORDER BY collected_at DESC,id DESC LIMIT 1''',version_id)
    if not snapshot:
        return dict(version=dict(version),snapshot=None,articles=[],supplements=[])
    return dict(version=dict(version),snapshot=dict(snapshot),
        articles=[dict(r) for r in await pool.fetch('SELECT * FROM law_history.articles WHERE snapshot_id=$1 ORDER BY source_order',snapshot['id'])],
        supplements=[dict(r) for r in await pool.fetch('SELECT * FROM law_history.supplements WHERE snapshot_id=$1 ORDER BY source_order',snapshot['id'])])


async def compare(left,right):
    pool = await get_pool()
    meta = await pool.fetch('SELECT id,law_id FROM law_history.versions WHERE id=ANY($1::bigint[])',[left,right])
    if len(meta)!=2 or len({r['law_id'] for r in meta})!=1:
        raise ValueError('Compare two distinct versions of the same law')
    texts=[]
    for vid in (left,right):
        sid=await pool.fetchval('SELECT id FROM law_history.snapshots WHERE version_id=$1 ORDER BY collected_at DESC,id DESC LIMIT 1',vid)
        if not sid:
            raise ValueError('Version body not collected')
        rows=await pool.fetch('SELECT body FROM law_history.articles WHERE snapshot_id=$1 ORDER BY source_order',sid)
        texts.append('\n\n'.join(r['body'] for r in rows).splitlines())
    return '\n'.join(difflib.unified_diff(*texts,fromfile=str(left),tofile=str(right),lineterm=''))

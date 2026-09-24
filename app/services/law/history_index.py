"""Derived archive indexes only. No changes to current-law tables or graph labels."""
import asyncio
import hashlib
import json
import math

import config
from app.database import get_pool
from app.services.embedding_service import embed_texts
from app.services.graph.store import connect
from app.services.law.relation_extractor import extract_relations

INDEX_LOCK = 2026092404
CHUNK_SIZE = 1200
CHUNK_STEP = 1100


def chunks(body):
    return [(offset, body[offset:offset + CHUNK_SIZE])
            for offset in range(0, len(body), CHUNK_STEP)]


def model_key():
    # Changing model weights under the same tag requires an explicit revision bump.
    return json.dumps([config.EMBEDDING_PROVIDER, config.EMBEDDING_MODEL,
                       config.EMBEDDING_VERSION, config.EMBED_DIM, 'history-body-v1'], separators=(',', ':'))


async def prepare():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''INSERT INTO law_history.index_texts(key,body,kind)
            SELECT DISTINCT ON(content_hash) 'a:'||content_hash,body,'article'
            FROM law_history.articles a WHERE unit_kind=$1
              AND NOT EXISTS(SELECT 1 FROM law_history.index_texts t WHERE t.key='a:'||a.content_hash)
            ON CONFLICT DO NOTHING''', '조문')
        await conn.execute('''INSERT INTO law_history.index_texts(key,body,kind)
            SELECT DISTINCT ON(body) 's:'||encode(sha256(convert_to(body,'UTF8')),'hex'),body,'supplement'
            FROM law_history.supplements s WHERE btrim(body)<>'' AND NOT EXISTS(
                SELECT 1 FROM law_history.index_texts t WHERE t.key='s:'||encode(sha256(convert_to(s.body,'UTF8')),'hex'))
            ON CONFLICT DO NOTHING''')
        while True:
            rows = await conn.fetch('SELECT key,body FROM law_history.index_texts WHERE NOT chunked ORDER BY key LIMIT 200')
            if not rows:
                break
            async with conn.transaction():
                for row in rows:
                    for position, body in chunks(row['body']):
                        key = hashlib.sha256(body.encode()).hexdigest()
                        await conn.execute('INSERT INTO law_history.search_chunks(key,body) VALUES($1,$2) ON CONFLICT DO NOTHING', key, body)
                        await conn.execute('INSERT INTO law_history.text_chunks VALUES($1,$2,$3) ON CONFLICT DO NOTHING', row['key'],key,position)
                    await conn.execute('UPDATE law_history.index_texts SET chunked=true WHERE key=$1', row['key'])
            print('PREPARED',len(rows),flush=True)


async def embed(limit=None, retry_failed=False, version_id=None):
    pool = await get_pool()
    selected=None
    if version_id is not None:
        sid=await pool.fetchval('SELECT id FROM law_history.snapshots WHERE version_id=$1 ORDER BY collected_at DESC,id DESC LIMIT 1',version_id)
        if sid is None:
            raise ValueError('Unknown collected version')
        rows=await pool.fetch('''SELECT DISTINCT chunk_key FROM law_history.text_chunks WHERE text_key IN (
            SELECT 'a:'||content_hash FROM law_history.articles WHERE snapshot_id=$1 AND unit_kind=$2
            UNION SELECT 's:'||encode(sha256(convert_to(body,'UTF8')),'hex') FROM law_history.supplements WHERE snapshot_id=$1)''',sid,'조문')
        selected=[r['chunk_key'] for r in rows]
    count = 0
    while limit is None or count < limit:
        rows = await pool.fetch('''SELECT key,body FROM law_history.search_chunks
            WHERE (embedding IS NULL OR model_key IS DISTINCT FROM $1)
              AND (error_type IS NULL OR $2) AND ($4::text[] IS NULL OR key=ANY($4)) ORDER BY key LIMIT $3''',
            model_key(),retry_failed,min(4,limit-count) if limit else 4,selected)
        if not rows:
            break
        try:
            vectors = await embed_texts([r['body'] for r in rows])
            if any(not all(math.isfinite(float(x)) for x in v) or not any(v) for v in vectors):
                raise ValueError('Invalid vector')
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany('''UPDATE law_history.search_chunks SET embedding=$2,
                        model_key=$3,attempts=attempts+1,error_type=NULL WHERE key=$1''',
                        [(r['key'],v,model_key()) for r,v in zip(rows,vectors)])
        except Exception as exc:
            await pool.executemany('''UPDATE law_history.search_chunks SET attempts=attempts+1,error_type=$2
                WHERE key=$1''',[(r['key'],type(exc).__name__) for r in rows])
            raise RuntimeError('HistoryEmbeddingBatchFailed') from None
        count += len(rows)
        if count % 100 == 0:
            print('EMBEDDED',count,flush=True)
        await asyncio.sleep(0.1)
    return count


async def graph():
    pool = await get_pool()
    async with connect() as driver:
        for label, prop in [('HistoryLaw','law_id'),('HistoryVersion','id'),('HistorySnapshot','id'),
                            ('HistoryText','key'),('HistoryLawName','name')]:
            await driver.execute_query(f'CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE',database_=config.NEO4J_DATABASE)
        # Explicit named references stay symbolic until query-time version/body verification.
        while True:
            rows = await pool.fetch('SELECT key,body,kind FROM law_history.index_texts WHERE NOT graph_done ORDER BY key LIMIT 200')
            if not rows:
                break
            texts, refs = [], []
            for row in rows:
                texts.append(dict(key=row['key'],kind=row['kind']))
                for ref in extract_relations(row['body']):
                    refs.append(dict(key=row['key'],name=''.join(ref['law_name'].split()),
                                     article=ref['article_no'],reference=ref['reference'],evidence=ref['evidence']))
            async with driver.session(database=config.NEO4J_DATABASE) as session:
                async def write(tx):
                    await (await tx.run('UNWIND $rows AS row MERGE (n:HistoryText {key:row.key}) SET n.kind=row.kind',rows=texts)).consume()
                    await (await tx.run('''UNWIND $rows AS row MATCH (s:HistoryText {key:row.key})
                        MERGE (t:HistoryLawName {name:row.name})
                        MERGE (s)-[r:MENTIONS {reference:row.reference}]->(t)
                        SET r.article_no=row.article,r.evidence=row.evidence,
                            r.basis='explicit_named_reference',r.legal_applicability_verified=false''',rows=refs)).consume()
                await session.execute_write(write)
            await pool.execute('UPDATE law_history.index_texts SET graph_done=true WHERE key=ANY($1::text[])',[r['key'] for r in rows])
        rows = await pool.fetch('''SELECT s.id AS snapshot_id,s.version_id,s.content_hash,s.source_url,
            v.law_id,v.law_name,v.mst,v.effective_date,v.promulgation_date,
            seq.previous_observed_version_id FROM law_history.snapshots s
            JOIN law_history.versions v ON v.id=s.version_id
            JOIN law_history.version_sequence seq ON seq.id=v.id
            WHERE NOT EXISTS(SELECT 1 FROM law_history.graph_progress p WHERE p.snapshot_id=s.id)
            ORDER BY s.id''')
        for row in rows:
            sid = row['snapshot_id']
            members = [dict(r) for r in await pool.fetch('''SELECT 'a:'||content_hash AS key,
                source_order,article_number,article_branch,title,'article' AS kind FROM law_history.articles
                WHERE snapshot_id=$1 AND unit_kind=$2 UNION ALL
                SELECT 's:'||encode(sha256(convert_to(body,'UTF8')),'hex'),source_order,'','','','supplement' FROM law_history.supplements
                WHERE snapshot_id=$1 AND btrim(body)<>'' ''',sid,'조문')]
            meta = dict(id=row['version_id'],law_id=row['law_id'],law_name=row['law_name'],
                        mst=row['mst'],effective=str(row['effective_date']),published=str(row['promulgation_date'] or ''),
                        snapshot=sid,hash=row['content_hash'],url=row['source_url'],previous=row['previous_observed_version_id'])
            async with driver.session(database=config.NEO4J_DATABASE) as session:
                async def write_snapshot(tx):
                    await (await tx.run('''MERGE (l:HistoryLaw {law_id:$m.law_id})
                        MERGE (v:HistoryVersion {id:$m.id}) SET v.law_name=$m.law_name,v.mst=$m.mst,
                          v.effective_on=$m.effective,v.published_on=$m.published
                        MERGE (l)-[:HAS_VERSION]->(v)
                        MERGE (s:HistorySnapshot {id:$m.snapshot}) SET s.content_hash=$m.hash,s.source_url=$m.url
                        MERGE (v)-[:HAS_SNAPSHOT]->(s)
                        FOREACH (id IN CASE WHEN $m.previous IS NULL THEN [] ELSE [$m.previous] END |
                          MERGE (p:HistoryVersion {id:id}) MERGE (v)-[:PREVIOUS_OBSERVED_VERSION]->(p))''',m=meta)).consume()
                    await (await tx.run('''MATCH (s:HistorySnapshot {id:$sid})
                        UNWIND $rows AS row MATCH (t:HistoryText {key:row.key})
                        MERGE (s)-[r:HAS_UNIT {kind:row.kind,source_order:row.source_order}]->(t)
                        SET r.article_number=row.article_number,r.article_branch=row.article_branch,r.title=row.title''',sid=sid,rows=members)).consume()
                await session.execute_write(write_snapshot)
            await pool.execute('INSERT INTO law_history.graph_progress(snapshot_id) VALUES($1) ON CONFLICT DO NOTHING',sid)
            print('GRAPH SNAPSHOT',sid,flush=True)
        aliases=await pool.fetch('''SELECT replace(law_name,' ','') AS name,min(law_id) AS law_id
            FROM law_history.versions GROUP BY 1 HAVING count(DISTINCT law_id)=1''')
        await driver.execute_query('''UNWIND $rows AS row
            MATCH (n:HistoryLawName {name:row.name}),(l:HistoryLaw {law_id:row.law_id})
            MERGE (n)-[:IDENTIFIES]->(l)''',rows=[dict(r) for r in aliases],database_=config.NEO4J_DATABASE)
        # Reuse verified current family identity without claiming historical family validity.
        await driver.execute_query('''MATCH (h:HistoryLaw),(c:TaxLaw) WHERE h.law_id=c.law_id
            MERGE (h)-[r:SAME_OFFICIAL_LAW]->(c) SET r.basis='official_id',
            r.historical_family_applicability_verified=false''',database_=config.NEO4J_DATABASE)


async def status():
    pool = await get_pool()
    return dict(await pool.fetchrow('''SELECT
        (SELECT count(*) FROM law_history.index_texts) AS texts,
        (SELECT count(*) FROM law_history.index_texts WHERE NOT chunked) AS unprepared,
        (SELECT count(*) FROM law_history.search_chunks) AS chunks,
        (SELECT count(*) FROM law_history.search_chunks WHERE embedding IS NOT NULL AND model_key=$1) AS embedded,
        (SELECT count(*) FROM law_history.search_chunks WHERE error_type IS NOT NULL) AS failed,
        (SELECT count(*) FROM law_history.graph_progress) AS graph_snapshots,
        (SELECT count(*) FROM law_history.snapshots) AS snapshots''',model_key()))

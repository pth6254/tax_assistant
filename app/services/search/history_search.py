"""Version-bound archive retrieval. Never substitute current law for missing history."""
import asyncio
from datetime import date
import re

from neo4j import Query
import config
from app.database import get_pool
from app.services.embedding_service import embed_texts
from app.services.graph.store import connect
from app.services.law.history_index import model_key
from app.services.law.reference_parser import extract_law_reference, format_article_no, parse_law_reference
from app.services.law.structure_parser import resolve_reference_target

NOTICE = ('아래 자료는 공포일·시행일을 기준으로 조회한 법령 버전의 원문 근거입니다. '
          '사건·귀속기간에 적용되는 법령을 확정한 것은 아닙니다. 부칙의 적용례·경과조치와 사실관계에 대한 별도 검토가 필요합니다.')


class HistoryUnavailable(ValueError):
    pass


def temporal_request(query):
    return bool(re.search(r'법령\s*버전\s*\d+|\d{4}[-./]\d{1,2}[-./]\d{1,2}|'
                          r'\d{4}\s*년|과거\s*법|구법|종전|개정\s*전|당시',query))


def requested_date(query):
    matches = re.findall(r'(\d{4})\s*(?:[-./]|년)\s*(\d{1,2})\s*(?:[-./]|월)\s*(\d{1,2})(?:일)?',query)
    if len(set(matches)) != 1:
        raise HistoryUnavailable('법령명과 조회 기준일을 YYYY-MM-DD로 알려주세요. 연도만으로 적용 버전을 결정하지 않습니다.')
    try:
        return date(*map(int,matches[0]))
    except ValueError:
        raise HistoryUnavailable('유효한 조회 날짜를 YYYY-MM-DD 형식으로 입력해 주세요.') from None


async def select_version(law_id, day):
    pool = await get_pool()
    rows = await pool.fetch('''SELECT * FROM law_history.versions WHERE law_id=$1
        AND effective_date=(SELECT max(effective_date) FROM law_history.versions
            WHERE law_id=$1 AND effective_date<=$2 AND promulgation_date<=$2)
        AND promulgation_date<=$2 ORDER BY id''',law_id,day)
    if len(rows)!=1:
        choices=' / '.join(f'법령버전 {r["id"]} (공포 {r["promulgation_date"]}, MST {r["mst"]})' for r in rows[:5])
        raise HistoryUnavailable('해당 날짜의 버전을 하나로 확정할 수 없습니다. '+(choices or '공식 원문 또는 다른 기준일을 확인해 주세요.'))
    return await with_snapshot(dict(rows[0]))


async def with_snapshot(version):
    pool=await get_pool()
    snapshot=await pool.fetchrow('SELECT * FROM law_history.snapshots WHERE version_id=$1 ORDER BY collected_at DESC,id DESC LIMIT 1',version['id'])
    if not snapshot or version['fetch_status']!='complete':
        raise HistoryUnavailable('요청한 버전 원문이 수집되지 않았습니다. 현행법으로 대체하지 않습니다.')
    return version | {'snapshot_id':snapshot['id'],'source_url':snapshot['source_url'],'snapshot_hash':snapshot['content_hash']}


async def query_version(query):
    pool=await get_pool()
    explicit=re.findall(r'법령\s*버전\s*(\d+)',query)
    if explicit:
        if len(set(explicit))!=1:
            raise HistoryUnavailable('한 번에 하나의 법령버전을 지정해 주세요.')
        row=await pool.fetchrow('SELECT * FROM law_history.versions WHERE id=$1',int(explicit[0]))
        if not row:
            raise HistoryUnavailable('해당 법령버전이 없습니다.')
        version=await with_snapshot(dict(row))
        if re.search(r'\d{4}[-./]\d|\d{4}\s*년',query):
            day=requested_date(query)
            if version['effective_date']>day or not version['promulgation_date'] or version['promulgation_date']>day:
                raise HistoryUnavailable('지정한 법령버전의 공포일·시행일이 조회 기준일보다 늦습니다. 날짜와 버전을 확인해 주세요.')
            return version,day
        return version, version['effective_date']
    day=requested_date(query)
    names=await pool.fetch('SELECT DISTINCT law_id,law_name FROM law_history.versions')
    compact=''.join(query.split())
    found=[r for r in names if ''.join(r['law_name'].split()) in compact]
    found=[r for r in found if not any(len(t['law_name'].replace(' ',''))>len(r['law_name'].replace(' ',''))
             and r['law_name'].replace(' ','') in t['law_name'].replace(' ','') for t in found)]
    ids={r['law_id'] for r in found}
    if len(ids)!=1:
        raise HistoryUnavailable('조회할 법령명을 하나 지정해 주세요. 예: 2010-01-01 기준 소득세법 제1조 원문')
    return await select_version(ids.pop(),day),day


def evidence(row, version, kind='article', graph_evidence=''):
    label=format_article_no(row['article_number'],row['article_branch']) if kind=='article' else '부칙'
    return dict(content=row['body'],article_no=label,law_name=version['law_name'],
        version_id=version['id'],snapshot_id=version['snapshot_id'],text_key=row['text_key'],
        effective_date=str(version['effective_date']),promulgation_date=str(version['promulgation_date']),
        source_url=version['source_url'],kind=kind,graph_evidence=graph_evidence)


async def direct_article(version, reference):
    pool=await get_pool()
    rows=await pool.fetch('''SELECT *, 'a:'||content_hash AS text_key FROM law_history.articles
        WHERE snapshot_id=$1 AND article_number=$2 AND article_branch=$3 AND unit_kind=$4''',
        version['snapshot_id'],str(reference.article),str(reference.article_branch or ''),'조문')
    if len(rows)!=1:
        raise HistoryUnavailable('해당 버전에서 요청한 조문을 유일하게 확인하지 못했습니다.')
    target=resolve_reference_target(rows[0]['body'],reference)
    if target is not None and not target.exists:
        raise HistoryUnavailable('해당 버전에 요청한 항·호·목이 없습니다. 현행 조문으로 대체하지 않습니다.')
    return evidence(rows[0],version)


async def semantic(version,query):
    pool=await get_pool()
    # Snapshot-local completeness: partial vector coverage cannot masquerade as not_found.
    keys=await pool.fetch('''SELECT DISTINCT 'a:'||content_hash AS key FROM law_history.articles
        WHERE snapshot_id=$1 AND unit_kind=$2 UNION SELECT 's:'||encode(sha256(convert_to(body,'UTF8')),'hex')
        FROM law_history.supplements WHERE snapshot_id=$1 AND btrim(body)<>'' ''',version['snapshot_id'],'조문')
    wanted=[r['key'] for r in keys]
    missing=await pool.fetchval('''SELECT count(*) FROM unnest($1::text[]) k
        LEFT JOIN law_history.index_texts t ON t.key=k
        WHERE t.key IS NULL OR NOT t.chunked OR EXISTS (
            SELECT 1 FROM law_history.text_chunks m JOIN law_history.search_chunks c ON c.key=m.chunk_key
            WHERE m.text_key=k AND (c.embedding IS NULL OR c.model_key IS DISTINCT FROM $2))''',wanted,model_key())
    if missing:
        raise HistoryUnavailable('해당 버전의 임베딩 색인이 아직 준비 중입니다. 조문번호를 지정하면 원문을 직접 조회할 수 있습니다.')
    vector=(await embed_texts([query]))[0]
    hits=await pool.fetch('''SELECT m.text_key,c.body,1-(c.embedding <=> $2::vector) AS score
        FROM law_history.text_chunks m JOIN law_history.search_chunks c ON c.key=m.chunk_key
        WHERE m.text_key=ANY($1::text[]) AND c.model_key=$3 AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> $2::vector LIMIT 5''',wanted,vector,model_key())
    result=[]
    for hit in hits:
        if hit['score']<config.SIMILARITY_THRESHOLD:
            continue
        if hit['text_key'].startswith('a:'):
            row=await pool.fetchrow('''SELECT *, 'a:'||content_hash AS text_key FROM law_history.articles
                WHERE snapshot_id=$1 AND content_hash=$2 AND unit_kind=$3 ORDER BY source_order LIMIT 1''',version['snapshot_id'],hit['text_key'][2:],'조문')
            item=evidence(row,version)
        else:
            item=dict(content='',article_no='부칙',law_name=version['law_name'],version_id=version['id'],
                snapshot_id=version['snapshot_id'],text_key=hit['text_key'],effective_date=str(version['effective_date']),
                promulgation_date=str(version['promulgation_date']),source_url=version['source_url'],kind='supplement',graph_evidence='')
        item['content']='[검색된 원문 발췌 — 조문/부칙 전체가 아님]\n'+hit['body']
        result.append(item)
    return result


async def expand(results, day):
    if not results:
        return results
    pool=await get_pool()
    output=list(results)
    seen={(r['version_id'],r['article_no']) for r in results}
    async with connect() as driver:
        for seed in results[:2]:
            # Verify snapshot identity and membership in PG again before using graph edges.
            snapshot_hash=await pool.fetchval('SELECT content_hash FROM law_history.snapshots WHERE id=$1',seed['snapshot_id'])
            records,_,_=await driver.execute_query(Query('''MATCH (s:HistorySnapshot {id:$sid})-[:HAS_UNIT]->
                (t:HistoryText {key:$key})-[r:MENTIONS]->(l:HistoryLawName)
                WHERE s.content_hash=$hash
                RETURN DISTINCT l.name AS law_name,r.reference AS reference,r.evidence AS evidence
                ORDER BY law_name,reference LIMIT 12''',timeout=2),sid=seed['snapshot_id'],key=seed['text_key'],hash=snapshot_hash,
                database_=config.NEO4J_DATABASE,routing_='r')
            for ref in records:
                ids=await pool.fetch('SELECT DISTINCT law_id FROM law_history.versions WHERE replace(law_name,\' \',\'\')=$1',ref['law_name'])
                if len(ids)!=1:
                    continue
                try:
                    version=await select_version(ids[0]['law_id'],day)
                    item=await direct_article(version,parse_law_reference(ref['reference']))
                except HistoryUnavailable:
                    continue
                if (item['version_id'],item['article_no']) in seen or len(item['content'].encode())>6000:
                    continue
                # Graph text must still occur in the immutable PG source, not just in Neo4j.
                original=await pool.fetchval('SELECT body FROM law_history.index_texts WHERE key=$1',seed['text_key'])
                if not original or ref['evidence'] not in original:
                    continue
                item['graph_evidence']=f'{seed["law_name"]} {seed["article_no"]}의 명시적 인용: {ref["evidence"]}'
                output.append(item)
                seen.add((item['version_id'],item['article_no']))
                if len(output)>=len(results)+2:
                    return output
    return output


async def retrieve(query):
    version,day=await query_version(query)
    ref=extract_law_reference(query)
    results=[await direct_article(version,ref)] if ref and ref.article is not None else await semantic(version,query)
    if not results:
        raise HistoryUnavailable('해당 버전에서 충분한 검색 근거를 찾지 못했습니다. 규정이 없다는 의미는 아닙니다.')
    graph_status='disabled'
    if config.HISTORY_GRAPH_RAG_ENABLED:
        pool=await get_pool()
        ready=await pool.fetchval('SELECT EXISTS(SELECT 1 FROM law_history.graph_progress WHERE snapshot_id=$1)',version['snapshot_id'])
        if ready:
            try:
                results=await asyncio.wait_for(expand(results,day),config.GRAPH_TIMEOUT_SEC)
                graph_status='checked'
            except Exception:
                graph_status='unavailable'
        else:
            graph_status='index_pending'
    return {'results':results,'graph_status':graph_status,'as_of':str(day),'notice':NOTICE,
            'legal_applicability_verified':False}

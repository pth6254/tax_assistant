"""Read-only archive audit; run in backend environment. Never repairs records."""
import asyncio
from collections import Counter
import hashlib
import json
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

from app.database import get_pool, close_pool
from app.services.law.history_parser import parse
from app.services.law.history_service import HistoryAPI


def passed(result):
    return (bool(result['coverage']) and not result['errors']
        and result['complete_without_snapshot'] == 0
        and result['blank_article_bodies'] == 0
        and all(c['discovery_status'] == 'complete' and c['expected_count'] == c['listed']
                and c['collected'] == c['listed'] and c['pending'] == c['failed'] == 0
                for c in result['coverage'])
        and len(result['official_samples']) == 3
        and all(s.get('raw_hash_match') and s.get('parsed_match') for s in result['official_samples']))


async def main(output_dir=None):
    pool = await get_pool()
    result = {'errors': {}, 'examples': {}, 'checked_snapshots': 0, 'official_samples': []}
    errors = Counter()
    samples = []
    def problem(kind, sid):
        errors[kind] += 1
        result['examples'].setdefault(kind, [])
        if len(result['examples'][kind]) < 5:
            result['examples'][kind].append(sid)
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            result['audited_at'] = str(await conn.fetchval('SELECT now()'))
            result['coverage'] = [dict(r) for r in await conn.fetch('SELECT * FROM law_history.coverage ORDER BY id')]
            result['latest_run'] = dict(await conn.fetchrow('SELECT * FROM law_history.runs ORDER BY id DESC LIMIT 1'))
            result['complete_without_snapshot'] = await conn.fetchval("""SELECT count(*) FROM law_history.versions v
                WHERE fetch_status='complete' AND NOT EXISTS(SELECT 1 FROM law_history.snapshots s WHERE s.version_id=v.id)""")
            result['article_units'] = await conn.fetchval('SELECT count(*) FROM law_history.articles')
            result['supplement_units'] = await conn.fetchval('SELECT count(*) FROM law_history.supplements')
            result['blank_article_bodies'] = await conn.fetchval("SELECT count(*) FROM law_history.articles WHERE btrim(body)=''")
            result['ambiguous_same_effective_date_groups'] = await conn.fetchval('''SELECT count(*) FROM
                (SELECT law_id,effective_date FROM law_history.versions GROUP BY 1,2 HAVING count(*)>1) x''')
            sample_ids = await conn.fetch('''SELECT DISTINCT ON (v.law_id) s.id FROM law_history.snapshots s
                JOIN law_history.versions v ON v.id=s.version_id
                WHERE v.law_id IN ('001565','003956','007507') ORDER BY v.law_id,v.effective_date,s.id''')
            wanted = {r['id'] for r in sample_ids}
            query = '''SELECT s.*,v.law_id,v.mst,v.effective_date,v.promulgation_date,v.promulgation_number,v.law_name
                FROM law_history.snapshots s JOIN law_history.versions v ON s.version_id=v.id ORDER BY s.id'''
            async for row in conn.cursor(query,prefetch=2):
                sid = row['id']
                xml = row['raw_xml']
                if hashlib.sha256(xml.encode()).hexdigest() != row['content_hash']:
                    problem('xml_hash',sid)
                try:
                    parsed = parse(xml,law_id=row['law_id'],effective_date=row['effective_date'],promulgation_date=row['promulgation_date'])
                    basic = ET.fromstring(xml).find('기본정보')
                    if (basic.findtext('공포번호') or '').lstrip('0') != row['promulgation_number'].lstrip('0'):
                        problem('promulgation_number',sid)
                    for table,key in [('articles','articles'),('supplements','supplements')]:
                        stored = await conn.fetch(f'SELECT * FROM law_history.{table} WHERE snapshot_id=$1 ORDER BY source_order',sid)
                        expected = parsed[key]
                        if len(stored)!=len(expected):
                            problem(table+'_count',sid)
                        elif any(any(actual[k] != value for k,value in item.items()) for actual,item in zip(stored,expected)):
                            problem(table+'_roundtrip',sid)
                except Exception as exc:
                    problem('parse_'+type(exc).__name__,sid)
                if sid in wanted:
                    samples.append(dict(row))
                result['checked_snapshots'] += 1
                if result['checked_snapshots'] % 300 == 0:
                    print('CHECKED',result['checked_snapshots'],flush=True)
    api = HistoryAPI()
    try:
        for row in samples:
            sample = dict(version_id=row['version_id'],law_name=row['law_name'],effective_date=str(row['effective_date']))
            try:
                fresh = await api.get('lawService.do',target='eflaw',MST=row['mst'],efYd=row['effective_date'].strftime('%Y%m%d'))
                sample['raw_hash_match'] = hashlib.sha256(fresh.encode()).hexdigest()==row['content_hash']
                sample['parsed_match'] = parse(fresh,law_id=row['law_id'],effective_date=row['effective_date'],promulgation_date=row['promulgation_date']) == parse(row['raw_xml'])
            except Exception as exc:
                sample['error_type'] = type(exc).__name__
            result['official_samples'].append(sample)
    finally:
        await api.close()
        await close_pool()
    result['errors'] = dict(errors)
    result['passed'] = passed(result)
    if output_dir:
        from datetime import datetime, timezone
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        report = directory / ('audit-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        with report.open('x', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False, default=str, indent=2)
        print('REPORT '+str(report), flush=True)
    print('RESULT '+json.dumps(result,ensure_ascii=False,default=str),flush=True)
    return result


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(main())

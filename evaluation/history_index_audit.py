"""Read-only PG/Neo4j membership audit for the derived historical graph."""
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime,timezone

import config
from app.database import get_pool,close_pool
from app.services.graph.store import connect
from app.services.law.history_index import status


async def main():
    pool=await get_pool()
    report=dict(index=await status(),errors=[],checked_snapshots=0)
    snapshots=await pool.fetch('SELECT id,version_id,content_hash FROM law_history.snapshots ORDER BY id')
    async with connect() as driver:
        for snapshot in snapshots:
            expected=await pool.fetch('''SELECT source_order,'article' AS kind,'a:'||content_hash AS key
                FROM law_history.articles WHERE snapshot_id=$1 AND unit_kind=$2 UNION ALL
                SELECT source_order,'supplement','s:'||encode(sha256(convert_to(body,'UTF8')),'hex')
                FROM law_history.supplements WHERE snapshot_id=$1 AND btrim(body)<>'' ''',snapshot['id'],'조문')
            rows,_,_=await driver.execute_query('''MATCH (v:HistoryVersion)-[:HAS_SNAPSHOT]->(s:HistorySnapshot {id:$id})
                OPTIONAL MATCH (s)-[r:HAS_UNIT]->(t:HistoryText)
                RETURN v.id AS version,s.content_hash AS hash,r.source_order AS position,r.kind AS kind,t.key AS key''',
                id=snapshot['id'],database_=config.NEO4J_DATABASE,routing_='r')
            actual={(r['position'],r['kind'],r['key']) for r in rows if r['key'] is not None}
            wanted={(r['source_order'],r['kind'],r['key']) for r in expected}
            if (not rows or any(r['version']!=snapshot['version_id'] or r['hash']!=snapshot['content_hash'] for r in rows)
                or actual!=wanted or sum(r['key'] is not None for r in rows)!=len(wanted)):
                report['errors'].append(snapshot['id'])
            report['checked_snapshots']+=1
            if report['checked_snapshots']%500==0:
                print('GRAPH CHECKED',report['checked_snapshots'],flush=True)
        records,_,_=await driver.execute_query('''MATCH (:HistoryText)-[r:MENTIONS]->(:HistoryLawName)
            RETURN count(r) AS mentions''',database_=config.NEO4J_DATABASE,routing_='r')
        report['mentions']=records[0]['mentions']
    report['graph_passed']=not report['errors'] and len(snapshots)==report['index']['graph_snapshots']
    report['embedding_complete']=(report['index']['chunks']>0 and report['index']['chunks']==report['index']['embedded']
                                  and report['index']['failed']==0 and report['index']['unprepared']==0)
    report['audited_at']=datetime.now(timezone.utc).isoformat()
    directory=Path('evaluation/runs/law-history-index')
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/('graph-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    await close_pool()


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(main())

"""Local live history retrieval/generation smoke. No user chat history writes."""
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from unittest.mock import AsyncMock,patch

import config
from app.database import close_pool
from app.services.graph.store import connect
from app.services.search.history_search import retrieve
from app.services.law.reference_parser import format_article_no
from app.services import chat_service
from app.services.llm_client import close_llm_client
from app.services.embedding_service import close_http_client


async def main():
    config.HISTORY_GRAPH_RAG_ENABLED=True
    async with connect() as driver:
        rows,_,_=await driver.execute_query('''MATCH (v:HistoryVersion)-[:HAS_SNAPSHOT]->(s:HistorySnapshot)
            -[u:HAS_UNIT]->(:HistoryText)-[:MENTIONS]->(:HistoryLawName)
            WHERE u.kind='article' AND v.effective_on<'2020-01-01' AND v.effective_on>'2000-01-01'
            RETURN DISTINCT v.id AS id,u.article_number AS article,u.article_branch AS branch LIMIT 30''',database_=config.NEO4J_DATABASE,routing_='r')
    attempts=[]
    selected=None
    for row in rows:
        query=f'법령버전 {row["id"]} {format_article_no(row["article"],row["branch"])} 원문을 설명해줘'
        try:
            result=await retrieve(query)
            added=sum(bool(r['graph_evidence']) for r in result['results'])
            attempts.append(dict(query=query,graph=result['graph_status'],added=added))
            if added:
                selected=query
                break
        except Exception as exc:
            attempts.append(dict(query=query,error=type(exc).__name__))
    report=dict(attempts=attempts,query=selected)
    try:
        semantic=await retrieve('법령버전 529 소득세 납세의무를 설명해줘')
        report['semantic_probe']=[dict(version_id=r['version_id'],article=r['article_no'],kind=r['kind']) for r in semantic['results']]
    except Exception as exc:
        report['semantic_probe_error']=type(exc).__name__
    if selected:
        with patch.object(chat_service,'_fetch_history',AsyncMock(return_value=[])),patch.object(chat_service,'_save_history',AsyncMock()):
            events=[]
            answer,_=await chat_service.process_chat(selected,str(uuid4()),str(uuid4()),tool_events=events)
            report.update(answer=answer,events=events,history_writes=False)
    directory=Path('evaluation/runs/law-history-index')
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/('smoke-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    await close_http_client()
    await close_llm_client()
    await close_pool()


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(main())

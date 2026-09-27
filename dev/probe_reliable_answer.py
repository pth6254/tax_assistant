"""Explicit live smoke: real models/search, no chat history or source DB writes.

Run inside the latest backend image. Output contains the supplied public example
and retrieved public law snapshots; do not use private queries without review.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path.cwd()))
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from langsmith import tracing_context
from app.services import chat_service as chat
from evaluation.adapters import close_live_clients

QUESTION = '''H건설회사는 I컨설팅회사로부터 총 5억 원의 경영컨설팅을 제공받았다고 주장하면서 세금계산서를 수취하였다.
그러나 세무조사 결과 I회사는 직원이 1명뿐이고 별도의 사무실도 존재하지 않았다.
컨설팅 보고서는 약 20페이지이며 내용 대부분이 인터넷에서 확인할 수 있는 일반적인 시장자료였다.
H사는 컨설팅 대금 5억 원을 지급한 직후 I회사의 대표가 해당 금액 중 4억 원을 현금으로 인출했다.
해당 거래의 실질을 판단하기 위해 어떤 자료를 확인해야 하는가?
거래가 가공거래로 판단되는 경우 H회사와 I회사에 각각 발생할 수 있는 법인세 및 부가가치세 문제를 설명하시오.'''


async def main(output):
    import config
    events = []
    def progress(event):
        events.append(event)
        print(json.dumps({k: event[k] for k in ('type', 'status', 'issue_id') if k in event}), flush=True)
    try:
        with tracing_context(enabled=False):
            async with asyncio.timeout(480):
                context, _, _, calc = await chat._fetch_rag_and_web_context(
                    QUESTION, uuid4(), str(uuid4()), history_override=[], on_tool_event=progress)
                print(json.dumps({'stage': 'prepared', 'evidence': len(context.records),
                                  'issues': len(context.plan.issues), 'plan_status': context.plan.status}), flush=True)
                answer, verification = await chat._answer_evidence_context(QUESTION, context, calc, str(uuid4()), progress)
        result = {'question': QUESTION, 'answer': answer, 'verification': verification,
                  'runtime': {'openrouter': config.LLM_PROVIDER == 'openrouter',
                              'luna': config.CHAT_MODEL == 'openai/gpt-6-luna',
                              'ollama_embedding': config.EMBEDDING_V1_PROVIDER == 'ollama'}}
        with Path(output).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'completed': True, 'status': verification['status'], 'metrics': verification.get('metrics'),
                          'runtime': result['runtime'], 'judge_error': verification.get('judge_error')}), flush=True)
    finally:
        await close_live_clients()


async def inspect_originals():
    from app.services.law.lookup_service import get_law_article
    try:
        for law, reference in [('부가가치세법', '제60조'), ('법인세법', '제19조'), ('부가가치세법', '제39조')]:
            article = await get_law_article(law, reference)
            print(json.dumps({'law': law, 'reference': reference, 'chars': len(article.article_text) if article else 0,
                              'has_item_1': bool(article and '1.' in article.article_text),
                              'source_id_present': bool(article and article.source_id)}, ensure_ascii=False))
    finally:
        await close_live_clients()


if __name__ == '__main__':
    asyncio.run(inspect_originals() if sys.argv[1] == '--inspect' else main(sys.argv[1]))

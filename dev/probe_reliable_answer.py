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


CASES = {
    'consulting': QUESTION,
    'financial': '금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?',
    'general': '부가가치세 매입세액 공제 요건과 공제받지 못하는 경우를 설명해줘.',
    'compound': '부모가 성년 자녀에게 현금을 증여할 때 공제 요건과 신고 절차, 준비할 서류를 설명해줘.',
    'dated_vat': '2025년에 온라인 쇼핑몰을 운영하는 개인사업자가 사업에 사용할 노트북을 구입하고 세금계산서를 받았습니다. 부가가치세 매입세액 공제를 받으려면 어떤 요건과 증빙을 확인해야 하고, 공제받지 못하는 경우는 무엇인가요?',
    'expense_items': '''IT기업 C사의 대표이사는 법인카드 외에도 자신의 개인 신용카드를 사용하고 매월 회사로부터 비용을 정산받았다.
세무조사 결과 다음 내역이 발견되었다.
고급 음식점 이용료 3,000만 원
골프장 이용료 2,000만 원
해외 호텔비 1,500만 원
자택 인터넷·통신비 500만 원
명품 구입비 1,000만 원
거래처 선물비 2,000만 원
회사는 모두 영업활동비 또는 복리후생비로 처리하였다.
대표이사는 음식점·골프·호텔 사용 중 상당 부분이 거래처 접대였다고 주장하지만 참석자 명단이나 회의자료는 없다.
각 비용의 손금 인정 가능성을 판단하고, 비용이 부인될 경우 대표이사에 대한 상여처분 여부를 검토하시오.
또한 부가가치세 매입세액 공제와 증빙불비 관련 가산세 문제도 함께 설명해줘.''',
}


async def main(output, case='consulting'):
    import config
    from app.services.calculator import formula_workflow
    from app.services.answer_verification import unavailable_verification
    from app.services.llm_client import _get_provider
    async def response_status(response):
        if not response.is_error:
            return
        await response.aread()
        # Diagnostic flags only: never dump response bodies, headers or keys.
        body = response.text.lower()
        try:
            error = response.json().get('error', {})
            message = str(error.get('message', ''))
            upstream = error.get('metadata', {}).get('raw', '')
            if upstream:
                try:
                    upstream = json.loads(upstream) if isinstance(upstream, str) else upstream
                    message += ': ' + str(upstream.get('error', {}).get('message', ''))
                except (ValueError, AttributeError):
                    pass
            for settings in config.LLM_TASK_SETTINGS.values():
                if settings.api_key:
                    message = message.replace(settings.api_key, '[REDACTED]')
        except (ValueError, AttributeError):
            message = ''
        print(json.dumps({'upstream_status': response.status_code,
                          'message': message[:500],
                          'schema_error': 'schema' in body,
                          'enum_error': 'enum' in body,
                          'grammar_error': 'grammar' in body,
                          'empty_error': 'empty' in body,
                          'rate_limit': 'rate' in body,
                          'credit_error': 'credit' in body}), flush=True)
    client = getattr(_get_provider('question_planning'), '_client', None)
    if client is not None:
        client.event_hooks['response'].append(response_status)
    question = CASES[case]
    # Public smoke fixtures only: retain proposals/reviews for diagnosing a
    # rejected formula without publishing them in chat or tracing private input.
    formula_calls = []
    original_formula_llm = formula_workflow.call_llm_structured
    async def record_formula(messages, schema, **kwargs):
        value = await original_formula_llm(messages, schema, **kwargs)
        formula_calls.append({'purpose': kwargs.get('purpose'), 'result': value})
        Path(output + '.formula.json').write_text(json.dumps(formula_calls, ensure_ascii=False, indent=2), encoding='utf-8')
        return value
    formula_workflow.call_llm_structured = record_formula
    events = []
    def progress(event):
        events.append(event)
        print(json.dumps({k: event[k] for k in ('type', 'status', 'issue_id') if k in event}), flush=True)
    try:
        with tracing_context(enabled=False):
            async with asyncio.timeout(480):
                context, _, _, calc = await chat._fetch_rag_and_web_context(
                    question, uuid4(), str(uuid4()), history_override=[], on_tool_event=progress)
                failure = chat._failed_tool_answer(events)
                if failure:
                    answer, verification = failure, unavailable_verification(events)
                else:
                    print(json.dumps({'stage': 'prepared', 'evidence': len(context.records),
                                      'issues': len(context.plan.issues) if context.plan else 0,
                                      'plan_status': context.plan.status if context.plan else 'tool_result'}), flush=True)
                    answer, verification = await chat._answer_evidence_context(question, context, calc, str(uuid4()), progress)
        result = {'question': question, 'answer': answer, 'verification': verification,
                  'runtime': {'openrouter': config.LLM_PROVIDER == 'openrouter',
                              'luna': config.CHAT_MODEL == 'openai/gpt-6-luna',
                              'ollama_embedding': config.EMBEDDING_V1_PROVIDER == 'ollama'}}
        with Path(output).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'completed': True, 'status': verification['status'], 'metrics': verification.get('metrics'),
                          'runtime': result['runtime'], 'judge_error': verification.get('judge_error')}), flush=True)
    finally:
        formula_workflow.call_llm_structured = original_formula_llm
        await close_live_clients()


async def inspect_originals():
    from app.services.law.lookup_service import get_law_article
    from app.database import get_pool
    from urllib.parse import urlparse, parse_qs
    try:
        for law, reference in [('부가가치세법', '제60조'), ('법인세법', '제19조'), ('부가가치세법', '제39조')]:
            article = await get_law_article(law, reference)
            pool = await get_pool()
            mst = parse_qs(urlparse(article.source_url).query).get('lsiSeq', [''])[0] if article else ''
            rows = await pool.fetch('''SELECT v.mst, v.effective_date, v.promulgation_date, s.id,
                length(s.raw_xml) AS xml_chars FROM law_history.versions v
                JOIN law_history.snapshots s ON s.version_id=v.id
                WHERE v.mst=$1 AND v.law_name=$2 ORDER BY v.effective_date DESC LIMIT 3''', mst, law)
            print(json.dumps({'law': law, 'reference': reference, 'chars': len(article.article_text) if article else 0,
                              'has_item_1': bool(article and '1.' in article.article_text),
                              'source_id_present': bool(article and article.source_id),
                              'effective_date': article.effective_date if article else None,
                              'snapshots': [dict(r) for r in rows]}, ensure_ascii=False, default=str))
    finally:
        await close_live_clients()


if __name__ == '__main__':
    asyncio.run(inspect_originals() if sys.argv[1] == '--inspect' else main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'consulting'))

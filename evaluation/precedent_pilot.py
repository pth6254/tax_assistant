"""Bounded, advisory precedent experiment; never approves reference cards.

Run inside the backend environment with an explicitly supplied collected batch.
No history reads/writes, private documents, cloud tracing or web search.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from evaluation.precedent_review import plain
from evaluation.schema import Dataset, Observation, digest
from evaluation.judge import assess, PROMPT


QUESTIONS = {
    '623075': '2020년 신규 주택을 취득할 때 기존 임차인이 거주하고 있었습니다. 취득 후 기존 임차인과 임대차기간을 연장했습니다. 구 소득세법 시행령(2021. 1. 5. 개정 전) 제155조 제1항 제2호 단서상 일시적 2주택 비과세 전입기한을 연장된 계약 종료일로 볼 수 있나요? 임대인 지위를 승계했다면 달라지나요?',
    '619463': '예식업체가 본점과 같은 곳에 있는 별도 사업장에서 생화 꽃 장식을 예식장에 설치해 예식 고객에게 공급했습니다. 구 부가가치세법 시행령(2019. 2. 12. 개정 전)이 적용되는 거래입니다. 별도 사업장으로 등록했고 꽃 소유권이 고객에게 이전된다면 면세인가요? 거래의 실질과 부수 공급 여부를 설명해주세요.',
    '622927': '구 법인세법(2018. 12. 24. 개정 전)과 구 법인세법 시행령(2019. 2. 12. 개정 전)이 적용되는 내국법인입니다. 국외사업장이 여러 국가에 있고 어느 국가에서 결손이 발생했습니다. 외국납부세액 공제한도 계산에서 그 결손을 국가별 국외원천소득에 어떻게 반영하나요? 한중 조세조약 제2의정서 제4조 때문에 한국 세법의 공제방법 적용이 배제되나요?',
    '621977': '구 법인세법(2018. 12. 24. 개정 전)이 적용되는 여신금융기관이 대부중개업자에게 법정 수수료 상한을 위반한 중개수수료를 지급했습니다. 실제 대출 수익을 얻기 위해 지출한 비용이라면 법인세 손금으로 인정받을 수 있나요? 일반적인 비용의 통상성과 수익 관련성을 구별해 설명해주세요.',
    '622257': '2019. 10. 13. 상속받은 토지를 개별공시지가로 평가해 상속세를 신고했습니다. 토지 절반씩을 2020. 9. 24.와 2021. 1. 15.에 매도했습니다. 과세관청이 이 매매가액을 상속 당시 시가로 삼으려면 무엇을 확인해야 하나요? 구 상속세 및 증여세법 시행령(2020. 2. 11. 개정 전) 제49조 제1항 단서에서 일반적인 가격 상승도 고려하는지, 가격변동이 없었다는 증명책임은 누구에게 있는지 알려주세요.',
}


def prepare(batch):
    dataset = Dataset.model_validate_json((batch / 'draft-cards.json').read_text(encoding='utf-8'))
    if {c.id for c in dataset.cases} != {'precedent-' + i for i in QUESTIONS}:
        raise ValueError('This pilot requires exactly the five reviewed source IDs')
    source_hashes = {}
    for case in dataset.cases:
        pid = case.id.removeprefix('precedent-')
        raw = (batch / (pid + '.json')).read_bytes()
        source = json.loads(raw)['PrecService']
        if str(source['사건번호']) != case.input['review_card']['case_number']:
            raise ValueError('Source case number mismatch')
        source_hashes[pid] = hashlib.sha256(raw).hexdigest()
        case.input['query'] = QUESTIONS[pid]
        # Complete official holding, not an LLM-created reference or truncated body.
        case.input['context'] = plain(source['판결요지'])
        case.rubric[1].instruction = '질문에 명시한 구법의 적용 범위를 유지하고 현행법을 소급 적용하지 않는다. 선고일이나 과세기간을 새로 지어내지 않는다. 구법이라고 단순 언급했더라도 현행 규칙으로 결론을 바꾸면 fail이다. 자료 부족으로 판단을 유보하면 unknown이다.'
    return dataset, source_hashes


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')


async def collect(query):
    from app.services import chat_service as chat
    captured = {'retrieval': [], 'tool_events': []}
    original_search = chat.hybrid_search
    original_context = chat._fetch_rag_and_web_context

    async def search(*args, **kwargs):
        results = await original_search(*args, **kwargs)
        captured['retrieval'] = [r.model_dump(mode='json') if hasattr(r, 'model_dump') else vars(r) for r in results]
        return results

    async def context(*args, **kwargs):
        result = await original_context(*args, **kwargs)
        captured['context'], captured['web_context'] = result[:2]
        return result

    started = time.perf_counter()
    error = None
    # Use a fresh non-existent user: no access to any user's uploaded documents.
    with patch.object(chat, '_fetch_history', AsyncMock(return_value=[])), \
         patch.object(chat, '_save_history', AsyncMock()), \
         patch.object(chat, 'TAVILY_API_KEY', ''), \
         patch.object(chat, 'hybrid_search', search), \
         patch.object(chat, '_fetch_rag_and_web_context', context):
        try:
            answer, calc = await asyncio.wait_for(chat.process_chat(
                query, str(uuid4()), str(uuid4()), tool_events=captured['tool_events']), 300)
            captured.update(answer=answer, calculator=calc)
        except Exception as exc:
            error = type(exc).__name__
    return captured, error, time.perf_counter() - started


async def run(batch, output):
    # Do not export evaluation/legal text through ambient LangSmith tracing.
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    os.environ['LANGSMITH_TRACING'] = 'false'
    import config
    from evaluation.adapters import close_live_clients
    from app.services.inference.llm import create_llm_provider
    dataset, hashes = prepare(batch)
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'dataset.json', dataset.model_dump(mode='json'))
    result = dict(started_at=datetime.now(timezone.utc).isoformat(), diagnostic_only=True,
        human_gate_unchanged=True, source_hashes=hashes, dataset_hash=dataset.fingerprint(),
        model=config.CHAT_MODEL, provider=config.LLM_PROVIDER, graph_enabled=config.GRAPH_RAG_ENABLED,
        generation_context=config.OLLAMA_NUM_CTX, judge_context=16384, judge_input_budget_bytes=14000,
        reference_scope='complete official holding (판결요지), full body retained in source batch',
        web_search=False, history_persistence=False, http_ui_test=False,
        same_model_bias_possible=True, prompt_hash=digest(PROMPT), records=[])
    try:
        for case in dataset.cases:
            print('GENERATE ' + case.id, flush=True)
            payload, error, elapsed = await collect(case.input['query'])
            observation = Observation(case_id=case.id, payload=payload, error=error, elapsed_seconds=elapsed)
            result['records'].append(dict(case_id=case.id, observation=observation.model_dump(mode='json'), criteria=[]))
            save(output / 'experiment.json', result)
            print(f'GENERATED {case.id} error={error} seconds={elapsed:.1f}', flush=True)
    finally:
        await close_live_clients()
    provider = create_llm_provider(config.LLM_PROVIDER,
        base_url=config.OLLAMA_BASE_URL if config.LLM_PROVIDER == 'ollama' else config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY, model=config.CHAT_MODEL, timeout=120,
        thinking=False, num_ctx=16384, keep_alive=0)
    try:
        for case, record in zip(dataset.cases, result['records']):
            print('JUDGE ' + case.id, flush=True)
            record['criteria'] = await assess(provider, case, Observation.model_validate(record['observation']),
                diagnostic_draft=True, input_budget_bytes=14000)
            save(output / 'experiment.json', result)
    finally:
        await provider.close()
    result['counts'] = dict(Counter(c['verdict'] for r in result['records'] for c in r['criteria']))
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    save(output / 'experiment.json', result)
    lines = ['# 판례 5건 실제 채팅 파이프라인 진단', '',
        '공식 판결요지를 정답 근거로 사용한 초안 진단. 인간 승인·세무 정답률·Graph 개선 효과를 의미하지 않습니다.',
        '실제 검색/도구 선택/답변 생성/인용 검증 실행. 웹 검색·대화 저장은 차단했고 HTTP/UI 검증은 아닙니다.',
        '과거 시점 질문은 서비스 정책에 따라 Graph 확장이 생략될 수 있습니다. 동일 모델 자기평가 편향이 있습니다.', '',
        f"실행 GraphRAG 설정: {result['graph_enabled']}",
        f"Judge 항목 집계: {result['counts']}", '']
    for case, record in zip(dataset.cases, result['records']):
        obs = record['observation']
        lines += [f'## {case.id}', '', f'[공식 판결]({case.source_url})', '', '### 질문', '', case.input['query'], '',
            '### 실제 답변', '', obs['payload'].get('answer', f"생성 오류: {obs['error']}"), '',
            '### Judge 보조 판정', '']
        lines += [f"- {r['criterion_id']}: {r['verdict']} — {r['rationale']}" for r in record['criteria']]
        lines += ['', '### 비교 기준: 공식 판결요지 전체', '', case.input['context'], '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('DONE ' + json.dumps(result['counts']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Suppress application logs that may contain raw provider errors or requests.
    logging.disable(logging.CRITICAL)
    asyncio.run(run(args.batch, args.output))

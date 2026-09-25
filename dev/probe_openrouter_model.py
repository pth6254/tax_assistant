"""Run non-sensitive, read-only compatibility checks for an OpenRouter model.

Uses the project's actual provider adapter. Never prints credentials or model output.
"""
import argparse
import asyncio

import httpx

from config import LLM_BASE_URL, LLM_TIMEOUT_SEC, OPENROUTER_API_KEY
from app.services.inference.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.inference.llm.policy import llm_purpose
from app.services.inference.llm.errors import LLMRequestError


async def main(model: str, pipeline: bool = False) -> int:
    if not OPENROUTER_API_KEY:
        print('configuration_missing: OPENROUTER_API_KEY')
        return 2
    provider = OpenAICompatibleLLMProvider(
        base_url=LLM_BASE_URL, api_key=OPENROUTER_API_KEY, model=model,
        timeout=LLM_TIMEOUT_SEC, thinking=False, provider='openrouter',
    )
    messages = [{'role': 'user', 'content': 'Reply with the word OK.'}]
    structured_messages = [{'role': 'user', 'content': 'Return a JSON object with ok set to true.'}]
    schema = {
        'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
        'required': ['ok'], 'additionalProperties': False,
    }
    failed = False
    try:
        checks = (
            ('complete', lambda: provider.complete(messages, 0.0, 1024)),
            ('stream', lambda: _collect(provider.stream(messages, 0.0, 1024))),
            ('structured', lambda: provider.structured(structured_messages, schema, 0.0, 1024)),
        )
        for name, run in checks:
            try:
                result = await run()
                valid = result == {'ok': True} if name == 'structured' else bool(result.strip())
                print(f'{name}: {"ok" if valid else "invalid_output"}')
                failed |= not valid
            except httpx.HTTPStatusError as exc:
                print(f'{name}: HTTP {exc.response.status_code}')
                failed = True
            except LLMRequestError as exc:
                print(f'{name}: {exc.code}')
                failed = True
            except Exception as exc:
                print(f'{name}: {type(exc).__name__}')
                failed = True
        if pipeline:
            failed |= not await _pipeline_checks(provider)
    finally:
        await provider.close()
    return 1 if failed else 0


async def _collect(stream):
    return ''.join([chunk async for chunk in stream])


async def _pipeline_checks(provider):
    """Synthetic inputs only; schema/argument checks, NOT tax-answer evaluation."""
    from app.schemas.ai_output import CitationList
    from app.services.law.history_answer import Answer
    from app.services import llm_client
    from app.services.tools.planner import select_tool

    previous = llm_client._provider_instances.copy()
    for settings in llm_client.LLM_TASK_SETTINGS.values():
        llm_client._provider_instances[settings] = provider
    passed = True
    try:
        try:
            selection = await select_tool('종합소득 5000만원의 세금을 계산해줘')
            valid = selection == ('income_tax', {'income': 50000000})
            print(f'tool_selection: {"ok" if valid else "invalid_output"}')
            passed &= valid
        except Exception as exc:
            print(f'tool_selection: {type(exc).__name__}')
            passed = False
        fixtures = (
            ('citation_schema', CitationList, 'citation_extraction', 2048,
             '형식 검사입니다. [법률] 소득세법 제1조 한 건만 citations에 기록하세요.'),
            ('history_schema', Answer, 'answer', 4096,
             '형식 검사이며 법률 자료가 아닙니다. 근거 1: 이것은 공개 검증용 예시 문장입니다. '
             'claims에 설명 하나, source=1, quote=이것은 공개 검증용 예시 문장입니다. 를 반환하세요.'),
        )
        for name, model, purpose, budget, prompt in fixtures:
            token = llm_purpose.set(purpose)
            try:
                data = await provider.structured([{'role': 'user', 'content': prompt}], model.model_json_schema(), 0, budget)
                result = model.model_validate(data)
                if name == 'history_schema':
                    assert len(result.claims) == 1 and result.claims[0].source == 1
                    assert result.claims[0].quote == '이것은 공개 검증용 예시 문장입니다.'
                else:
                    assert len(result.citations) == 1 and result.citations[0].article_no == '제1조'
                    assert result.citations[0].law_name == '소득세법'
                print(f'{name}: ok')
            except Exception as exc:
                print(f'{name}: {type(exc).__name__}')
                passed = False
            finally:
                llm_purpose.reset(token)
    finally:
        llm_client._provider_instances.clear()
        llm_client._provider_instances.update(previous)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model')
    parser.add_argument('--pipeline', action='store_true', help='Also check real tool extraction and citation/history schemas (paid calls)')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.model, args.pipeline)))

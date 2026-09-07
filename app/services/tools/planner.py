"""질문에서 도구 하나를 선택한다. provider 고유 tool_calls에는 의존하지 않는다."""
import asyncio
import json
import logging
import re

from app.schemas.tool_call import ToolSelection
from app.services.ai_pipeline import chat_prompt, structured_chain
from app.services.llm_client import call_llm
from app.services.law.reference_parser import extract_law_reference
from app.services.tools.registry import TOOL_SCHEMAS
from app.services.tools.executor import ToolRun, execute_tool

logger = logging.getLogger(__name__)
# 금액 표현: 숫자 또는 한글 단위(억/천만/백만/만원)
_AMOUNT_RE = re.compile(r"\d|[일이삼사오육칠팔구십백천]+\s*(?:억|천만|백만|만\s*원)")
# 계산 의도 키워드
_INTENT_RE = re.compile(r"얼마|계산|세액|세금.{0,6}(?:나오|내야|납부|부과)|내야\s*(?:하|할|되)")

def has_calculation_intent(query: str) -> bool:
    """금액 표현 + 계산 의도 키워드가 모두 있을 때만 True (LLM 호출 게이트)."""
    return bool(_AMOUNT_RE.search(query)) and bool(_INTENT_RE.search(query))



def has_tool_intent(query: str) -> bool:
    reference = extract_law_reference(query)
    return (
        has_calculation_intent(query)
        or bool(reference and reference.article is not None)
        or bool(re.search(r"원문|조문|문서|서류|계약서|업로드|첨부|PDF|pdf", query))
    )


async def select_tool(query: str, history: list[dict] | None = None) -> tuple[str, dict] | None:
    definitions = {name: schema.model_json_schema() for name, schema in TOOL_SCHEMAS.items()}
    prompt = chat_prompt(
        "세무 보조 도구를 최대 하나 선택하고 JSON만 출력하세요. "
        "원문 조회는 law_lookup, 내 업로드 문서 검색은 document_search. "
        "세액 계산은 income_tax(종합소득세), capital_gains(양도소득세), inheritance(상속세), "
        "gift(증여세), vat(부가가치세), penalty_tax(가산세)를 사용하세요. "
        "금액은 원 단위 정수로 변환하세요. 사용자와 이전 대화에 없는 필수 입력은 추측하지 마세요. "
        "도구가 불필요하거나 필수 입력이 없으면 {\"tool\":\"none\"}. "
        "사용자 신원이나 SQL은 인자로 넣지 마세요. "
        "법령명과 가지번호·항·호·목은 정확히 보존하세요. "
        "출력: {\"tool\":\"도구명\",\"params\":{입력값}}\n"
        + json.dumps(definitions, ensure_ascii=False),
        "{query}", history=True,
    )
    async def generate(messages):
        return await call_llm(messages, temperature=0.0, max_tokens=400)
    chain = structured_chain(prompt, generate, ToolSelection, name="tool_selection")
    data = await chain.ainvoke({"query": query, "history": (history or [])[-4:]})
    if data.tool == "none":
        return None
    return data.tool, data.params


async def run_tools_for_query(query: str, *, user_id: str, history: list[dict] | None = None, on_event=None) -> ToolRun | None:
    if not has_tool_intent(query) and not (
        history and re.search(r"계산|문서|조문|원문|다시|그럼", query)
    ):
        return None
    if on_event:
        on_event({"type": "tool", "id": "primary", "tool": "none", "status": "selecting"})
    try:
        async with asyncio.timeout(30):
            selection = await select_tool(query, history)
    except Exception as exc:
        logger.warning("Tool selection failed (%s)", type(exc).__name__)
        result = ToolRun("none", "selection_error", "도구 입력을 확정하지 못했습니다. 필요한 조건을 확인하고 결과를 추측하지 마세요.")
        _emit_result(result, {}, on_event)
        return result
    if selection is None:
        result = ToolRun("none", "needs_input", "실행할 도구나 필수 입력을 확정하지 못했습니다. 필요한 조건을 확인하고 세액·문서 내용을 추측하지 마세요.")
        _emit_result(result, {}, on_event)
        return result
    if on_event:
        on_event({"type": "tool", "id": "primary", "tool": selection[0], "status": "running"})
    result = await execute_tool(*selection, user_id=user_id)
    _emit_result(result, selection[1] if result.status == "ok" else {}, on_event)
    return result


def _emit_result(result, params, callback):
    if callback:
        callback({
            "type": "tool", "id": "primary", "tool": result.tool,
            "status": result.status,
            "error_code": result.error_code, "retryable": result.retryable,
            "params": result.calculation.params if result.calculation else params,
            "context": result.calculation.context if result.calculation else result.context,
        })

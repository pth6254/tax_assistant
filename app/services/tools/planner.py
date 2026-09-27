"""질문에서 도구 하나를 선택한다. provider 고유 tool_calls에는 의존하지 않는다."""
import asyncio
import json
import logging
import re
from dataclasses import replace

from app.schemas.tool_call import ToolSelection
from app.services.ai_pipeline import chat_prompt, structured_chain
from app.services.llm_client import call_llm
from app.services.inference.llm.errors import LLMRequestError
from app.services.law.reference_parser import extract_law_reference, parse_law_reference, InvalidLawReference
from app.services.law.coverage_service import NATIONAL_TAX_LAWS
from app.services.tools.registry import TOOL_SCHEMAS
from app.services.tools.executor import ToolRun, execute_tool
from app.services.tools.policy import DOCUMENT_INTENT, check_proposal

logger = logging.getLogger(__name__)
# 금액 표현: 숫자 또는 한글 단위(억/천만/백만/만원)
_AMOUNT_RE = re.compile(r"\d|[일이삼사오육칠팔구십백천]+\s*(?:억|천만|백만|만\s*원)")
# 세금계산서의 '계산'은 세액 산출 요청이 아니다.
_INTENT_RE = re.compile(r"얼마|계산(?!서)|세액|세금.{0,6}(?:나오|내야|납부|부과)|내야\s*(?:하|할|되)")

def has_calculation_intent(query: str) -> bool:
    """Explicit calculation requests may lack inputs; a year alone is not money."""
    without_dates = re.sub(r"\d{4}\s*(?:년|[-./]\d{1,2}[-./]\d{1,2})", "", query)
    explicit_request = bool(re.search(r"계산(?:\s*(?:해|부탁|좀)|\s*[.!?]*$)", query))
    return explicit_request or (bool(_AMOUNT_RE.search(without_dates)) and bool(_INTENT_RE.search(query)))



def has_tool_intent(query: str) -> bool:
    reference = extract_law_reference(query)
    return (
        has_calculation_intent(query)
        or bool(reference and reference.article is not None)
        or bool(re.search(r"원문|조문", query)) or bool(DOCUMENT_INTENT.search(query))
    )


async def select_tool(query: str, history: list[dict] | None = None) -> tuple[str, dict] | None:
    # Only an entire, unambiguous current-law reference bypasses the LLM.
    # Comparisons, dates, unnamed follow-ups and mixed tasks retain the planner.
    reference_text = re.sub(r"\s*(?:원문|조문)?\s*(?:보여\s*줘|보여주세요|조회(?:해\s*줘|해주세요)?)?\s*[?.!]*$", "", query.strip())
    try:
        reference = parse_law_reference(reference_text)
        known_names = {name + suffix for name in (*NATIONAL_TAX_LAWS, "지방세법")
                       for suffix in ("", " 시행령", " 시행규칙")}
        if reference.law_name in known_names:
            return "law_lookup", {"law_name": reference.law_name,
                                  "article_no": replace(reference, law_name=None).canonical}
    except InvalidLawReference:
        pass
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
        return await call_llm(messages, temperature=0.0, max_tokens=1024, purpose="tool_selection")
    chain = structured_chain(prompt, generate, ToolSelection, name="tool_selection")
    data = await chain.ainvoke({"query": query, "history": (history or [])[-4:]})
    if data.tool == "none":
        return None
    return data.tool, data.params


async def run_tools_for_query(query: str, *, user_id: str, history: list[dict] | None = None, on_event=None) -> ToolRun | None:
    last_question = next((m.get("content", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    # A changed amount after an actual calculation is a follow-up; "그럼" alone is not.
    calculation_followup = has_calculation_intent(last_question) and bool(
        re.search(r"\d[\d,.]*\s*(?:억|만|천|원)|다시\s*(?:해|계산)", query)
    )
    if not has_tool_intent(query) and not calculation_followup:
        return None
    if on_event:
        on_event({"type": "tool", "id": "primary", "tool": "none", "status": "selecting"})
    try:
        async with asyncio.timeout(30):
            selection = await select_tool(query, history)
    except LLMRequestError:
        raise  # Preserve rate-limit/credit/timeout classification for the UI.
    except Exception as exc:
        logger.warning("Tool selection failed (%s)", type(exc).__name__)
        result = ToolRun("none", "selection_error", "도구 입력을 확정하지 못했습니다. 필요한 조건을 확인하고 결과를 추측하지 마세요.")
        _emit_result(result, {}, on_event)
        return result
    if selection is None:
        if not (has_calculation_intent(query) or calculation_followup or DOCUMENT_INTENT.search(query)
                or re.search(r"원문.*(?:보여|조회)|조문.*조회", query)):
            if on_event:
                on_event({"type": "tool", "id": "primary", "tool": "none", "status": "no_tool_needed"})
            return None
        result = ToolRun("none", "needs_input", "실행할 도구나 필수 입력을 확정하지 못했습니다. 필요한 조건을 확인하고 세액·문서 내용을 추측하지 마세요.")
        _emit_result(result, {}, on_event)
        return result
    allowed, reason, proofs = check_proposal(*selection, query, history,
        calculation_intent=has_calculation_intent(query) or calculation_followup)
    if not allowed:
        # An irrelevant proposal for an analysis question must not suppress RAG.
        if reason in {"explicit_reference_required", "explicit_lookup_request_required", "document_request_required", "calculation_request_mismatch"} and not (
            has_calculation_intent(query) or calculation_followup or DOCUMENT_INTENT.search(query)
        ):
            if on_event:
                on_event({"type": "tool", "id": "primary", "tool": selection[0],
                          "status": "no_tool_needed", "error_code": reason})
            return None
        from app.services.tools.policy import ALIASES
        missing = reason.split(":", 1)[1].split(",") if reason.startswith("unconfirmed_inputs:") else []
        labels = [ALIASES.get(key, key).split("|")[0] for key in missing]
        result = ToolRun(selection[0], "invalid_arguments" if reason == "invalid_input" else "needs_input", "입력값 또는 조회 대상을 사용자 발언에서 확인하지 못했습니다."
                         + (" 확인할 입력: " + ", ".join(labels) if labels else " 조회 대상과 계산 조건을 구체적으로 알려주세요."),
                         error_code=reason)
        _emit_result(result, {}, on_event)
        return result
    if on_event:
        on_event({"type": "tool", "id": "primary", "tool": selection[0], "status": "running"})
    result = await execute_tool(*selection, user_id=user_id)
    _emit_result(result, selection[1], on_event)
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

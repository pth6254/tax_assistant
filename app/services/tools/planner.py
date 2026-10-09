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
from app.services.law.reference_parser import parse_law_reference, InvalidLawReference
from app.services.law.coverage_service import NATIONAL_TAX_LAWS
from app.services.tools.registry import TOOL_SCHEMAS
from app.services.tools.executor import ToolRun, execute_tool
from app.services.tools.policy import DOCUMENT_INTENT, CALC_TAX, ALIASES, check_proposal, has_lookup_intent
from app.services.tools.policy import financial_income_scope

logger = logging.getLogger(__name__)
_AMOUNT_RE = re.compile(r"(?:\d[\d,.]*|[일이삼사오육칠팔구십백천]+)\s*(?:억|천만|백만|천|만|원)")
_CALC_ACTION = re.compile(r"(?:계산|산출)(?:을|를)?\s*(?:해\s*(?:줘|주세요|봐)|해주세요|해라|하라|하시오|부탁|좀|[.!?]*$)")
_TAX_AMOUNT_QUESTION = re.compile(
    r"(?:세금|세액|납부액|환급액|소득세|양도세|상속세|증여세|부가세|부가가치세|가산세)"
    r"(?:은|는|이|가|을|를)?\s*얼마(?:나)?\s*(?:야|예요|인가|인지|입니까|나와|나오|내|납부|부과|되|정도|[?!]*$)"
)

def has_calculation_intent(query: str) -> bool:
    """Explicit calculation requests may lack inputs; a year alone is not money."""
    # Numbers, statutory references, credits and calculation methods describe
    # facts/topics. Require an actual request to produce a numeric result.
    return bool(_CALC_ACTION.search(query) or _TAX_AMOUNT_QUESTION.search(query) or (
        _AMOUNT_RE.search(query) and re.search(r"(?:세액|납부액|환급액)(?:을|를)?\s*(?:알려|구해)", query)
    ))


def is_calculation_followup(query, history):
    last_question = next((m.get("content", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    if not has_calculation_intent(last_question):
        return False
    return bool(re.fullmatch(
        r"\s*(?:(?:그럼|그러면|대신)\s*)?(?:(?:소득|수입|매출|매입|경비|증여액)(?:은|는|이|가|을|를)?\s*)?"
        r"\d[\d,.]*\s*(?:억|천만|백만|천|만)?\s*원?(?:이면|이라면|으로|으로 바꾸면)?\s*[?.!]*\s*", query
    ) and _AMOUNT_RE.search(query))



def has_tool_intent(query: str) -> bool:
    return (
        has_calculation_intent(query)
        or has_lookup_intent(query) or bool(DOCUMENT_INTENT.search(query))
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
        "세액 계산은 income_tax(종합소득세), financial_income_tax(이자·배당 금융소득이 있는 종합소득세), capital_gains(양도소득세), inheritance(상속세), "
        "gift(증여세), vat(부가가치세), penalty_tax(가산세)를 사용하세요. "
        "위 계산기의 지원 대상 밖인 세액 계산은 formula_calculation을 선택하고 params는 빈 객체로 두세요. "
        "일반 설명이나 기존 계산기의 단순 입력 부족을 formula_calculation으로 보내지 마세요. "
        "금액은 원 단위 정수로 변환하세요. 사용자와 이전 대화에 없는 필수 입력은 추측하지 마세요. "
        "설명·요건·절차·법적 분석처럼 도구가 불필요한 요청만 {\"tool\":\"none\"}. "
        "계산이나 조회를 명시적으로 요청했지만 입력이 부족하면 해당 도구와 확인된 인자만 반환하세요. "
        "입력 부족과 도구 불필요를 혼동하지 마세요. "
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
    # A changed amount after an actual calculation is a follow-up; "그럼" alone is not.
    calculation_followup = is_calculation_followup(query, history)
    if not has_tool_intent(query) and not calculation_followup:
        return None
    if (has_calculation_intent(query) or calculation_followup) and financial_income_scope(query, history):
        # The deterministic calculator answers when the amounts can be read; the model's
        # free-form formula is the fallback, not the first choice.
        result = await financial_calculation(query, history, on_event)
        if result is not None:
            return result
        return ToolRun("formula_calculation", "planned", "공식 근거를 확인한 산식으로 참고 계산을 준비합니다.")
    if on_event:
        on_event({"type": "tool", "id": "primary", "tool": "none", "status": "selecting"})
    try:
        async with asyncio.timeout(30):
            selection = await select_tool(query, history)
    except LLMRequestError:
        raise  # Preserve rate-limit/credit/timeout classification for the UI.
    except Exception as exc:
        logger.warning("Tool selection failed (%s)", type(exc).__name__)
        result = ToolRun("none", "selection_error", "요청을 처리할 도구를 선택하는 과정에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                         error_code="tool_selection_failed", retryable=True)
        _emit_result(result, {}, on_event)
        return result
    if selection is None:
        if DOCUMENT_INTENT.search(query):
            # An explicit document search already has its query; `none` is not
            # proof that a file or an input is missing. Ownership is checked by
            # the executor/search service as for a model-selected call.
            selection = ("document_search", {"query": query[:500]})
        elif not (has_calculation_intent(query) or calculation_followup or has_lookup_intent(query)):
            if on_event:
                on_event({"type": "tool", "id": "primary", "tool": "none", "status": "no_tool_needed"})
            return None
        else:
            if has_calculation_intent(query) or calculation_followup:
                matches = [tool for tool, pattern in CALC_TAX.items() if re.search(pattern, query, re.I)]
                tool = matches[0] if len(matches) == 1 else "none"
                fields = [ALIASES.get(key, key).split("|")[0] for key in TOOL_SCHEMAS[tool].model_fields] if tool != "none" else []
                message = ("세액 계산에 사용할 값을 확인해 주세요: " + ", ".join(fields) + "."
                           if fields else "계산할 세목과 계산에 사용할 금액·조건을 알려주세요.")
            else:
                tool, message = "law_lookup", "원문을 조회할 법령명과 조·항·호 번호를 알려주세요."
            result = ToolRun(tool, "needs_input", message, error_code="calculation_inputs_required" if has_calculation_intent(query) or calculation_followup else "lookup_target_required")
            _emit_result(result, {}, on_event)
            return result
    if selection[0] == 'formula_calculation':
        if has_calculation_intent(query) or calculation_followup:
            return ToolRun('formula_calculation', 'planned', '공식 근거를 확인한 산식으로 참고 계산을 준비합니다.')
        return None
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
        missing = reason.split(":", 1)[1].split(",") if reason.startswith("unconfirmed_inputs:") else []
        if reason == "missing_input":
            missing = [key for key in TOOL_SCHEMAS[selection[0]].model_fields if key not in selection[1]]
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


async def financial_calculation(query, history, on_event=None):
    """금융소득 종합과세 계산기 결과와 그 가정, or None to use the reference-formula path."""
    from app.services.calculator.engine import run_calculation
    from app.services.calculator.errors import CalculationError
    from app.services.calculator.financial_inputs import stated_financial_inputs
    from app.services.calculator.repository import get_deduction
    try:
        row = await get_deduction("소득세", "기본공제")
        stated = stated_financial_inputs(query, history, basic_deduction=int(row["amount"]) if row else None)
        if stated is None:
            return None
        if on_event:
            on_event({"type": "tool", "id": "primary", "tool": "financial_income_tax", "status": "running"})
        run = await run_calculation("financial_income_tax", stated.params)
    except (CalculationError, ValueError, KeyError, TypeError) as exc:
        logger.info("Financial income calculator not used (%s)", type(exc).__name__)
        return None
    # Assumptions lead the result: they change the amounts as much as the inputs do.
    run.context = "\n".join(["계산에 쓴 가정:", *[f"- {item}" for item in stated.assumptions], "", run.context]) \
        if stated.assumptions else run.context
    result = ToolRun("financial_income_tax", "ok", "", run)
    _emit_result(result, stated.params, on_event)
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

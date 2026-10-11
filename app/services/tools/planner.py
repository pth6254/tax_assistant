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
from app.services.tools.policy import DOCUMENT_INTENT, CALC_TAX, ALIASES, PENALTY, check_proposal, has_lookup_intent
from app.services.tools.policy import (capital_gains_scope, financial_income_scope, gift_scope, income_tax_scope,
                                       inheritance_scope, penalty_scope, retirement_scope, vat_scope,
                                       virtual_asset_scope)

logger = logging.getLogger(__name__)
PENALTY_WORD = PENALTY
_AMOUNT_RE = re.compile(r"(?:\d[\d,.]*|[일이삼사오육칠팔구십백천]+)\s*(?:억|천만|백만|천|만|원)")
_CALC_ACTION = re.compile(r"(?:계산|산출)(?:을|를)?\s*(?:해\s*(?:줘|주세요|봐)|해주세요|해라|하라|하시오|부탁|좀|[.!?]*$)")
_TAX_AMOUNT_QUESTION = re.compile(
    r"(?:세금|세액|납부액|환급액|소득세|양도세|상속세|증여세|부가세|부가가치세|가산세)"
    r"(?:은|는|이|가|을|를|까지)?"
    # "가산세 포함 얼마야", "가산세까지 합치면 얼마야": the total is still the asked amount.
    r"(?:\s*(?:포함(?:해서|하면|한|해)?|합쳐서|합치면|합하면|더해서|더하면|모두|전부|다\s*해서|총))*"
    r"\s*얼마(?:나)?\s*(?:야|예요|인가|인지|입니까|나와|나오|내|납부|부과|되|정도|[?!]*$)"
)
# Facts each calculator needs, asked in Korean when the question cannot be read into its inputs.
CALCULATOR_FACTS = {
    "income_tax": ("종합소득세", "소득 종류별 금액(근로소득 총급여, 사업소득 수입금액과 필요경비, 이자·배당, 주택임대 수입·보증금과 "
                              "주택 수, 종교인소득 등)과 기본공제 인원"),
    "retirement": ("퇴직소득세", "퇴직급여 금액과 근속연수(연금계좌로 옮기면 그 금액)"),
    "capital_gains": ("양도소득세", "양도가액, 취득가액, 보유기간, 자산 종류(주택이면 1세대 1주택 여부와 거주기간, 다주택이면 "
                                 "조정대상지역 여부)"),
    "gift": ("증여세", "증여액, 주는 사람과의 관계(직계존속이면 받는 사람이 미성년자인지), 10년 이내 같은 사람에게 받은 증여"),
    "inheritance": ("상속세", "상속재산 가액, 채무·장례비용, 배우자 유무와 배우자 상속액, 자녀 수"),
    "vat": ("부가가치세", "일반과세자인지 간이과세자인지(간이과세자면 업종), 매출액, 매입액"),
    "penalty_tax": ("가산세", "본세 금액, 무신고·과소신고·납부지연 중 무엇인지, 법정기한을 넘긴 기간"),
}
FOLLOWUP_AMOUNT = re.compile(r"(?:\d[\d,.]*\s*(?:억|천만|백만|천|만)\s*)+원?|\d[\d,]*\s*원")

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
        "세액 계산은 retirement(퇴직소득세), income_tax(근로·사업·기타·연금·이자·배당 소득의 종합소득세, 금융소득 종합과세와 "
        "가상자산소득 분리과세 포함), capital_gains(양도소득세), inheritance(상속세), gift(증여세), vat(부가가치세)를 사용하세요. "
        "기한을 넘긴 신고·납부는 각 계산기의 penalty_type 등 가산세 옵션으로 넣고, 본세 금액만 주어진 가산세 질문은 "
        "penalty_tax를 사용하세요. "
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
    if has_calculation_intent(query) or calculation_followup:
        calc_query = query
        if calculation_followup and not re.search(r"소득|수입|매출|매입|경비|증여액", query):
            calc_query = followup_question(query, history)
            if isinstance(calc_query, ToolRun):
                _emit_result(calc_query, {}, on_event)
                return calc_query
        result = await tax_calculation(calc_query, history, on_event)
        if result is not None:
            return result
        if penalty_scope(calc_query, history):
            # 본세를 말한 가산세 질문은 가산세만 계산한다. 본세 대신 세목 계산 사실을 말했으면
            # '가산세'를 뺀 질문으로 그 세목 계산기를 실행하고 가산세를 옵션으로 붙인다.
            result = await penalty_calculation(calc_query, history, on_event)
            if result is not None:
                return result
            result = await tax_calculation(PENALTY_WORD.sub("", calc_query), history, on_event, facts_query=calc_query)
            if result is not None:
                return result
        # The six calculators have readers; a model proposal for them is rejected by the input
        # proofs anyway, so no selection is paid for. Amounts the reader could not use mean a case
        # the calculator does not model (국외 자산, 창업자금 특례 …): the sourced reference formula
        # answers it. Without amounts the calculator's facts are asked.
        tool = calculator_in_scope(calc_query, history)
        if tool is not None and _AMOUNT_RE.search(calc_query):
            return ToolRun("formula_calculation", "planned", "공식 근거를 확인한 산식으로 참고 계산을 준비합니다.")
        if tool is not None:
            result = ask_calculator_facts(tool)
            _emit_result(result, {}, on_event)
            return result
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
                if tool in CALCULATOR_FACTS:
                    result = ask_calculator_facts(tool)
                    _emit_result(result, {}, on_event)
                    return result
                message = "계산할 세목과 계산에 사용할 금액·조건을 알려주세요."
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


def followup_question(query, history):
    """"그럼 7천만원이면?": the previous question with its one amount replaced, or a ToolRun asking which amount."""
    previous = next((m.get("content", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    new = FOLLOWUP_AMOUNT.search(query)
    amounts = [m for m in FOLLOWUP_AMOUNT.finditer(previous) if m.group().strip()]
    if new is None or not amounts:
        return query
    if len(amounts) > 1:
        stated = ", ".join(f"{(previous[:m.start()].split() or [''])[-1]} {m.group().strip()}".strip() for m in amounts)
        return ToolRun("none", "needs_input", f"이전 질문의 금액 가운데 어느 것을 {new.group().strip()}으로 바꿀지 알려주세요"
                       f"({stated}). 예: '매출 {new.group().strip()}이면?'", error_code="calculation_inputs_required")
    m = amounts[0]
    old = m.group().rstrip()
    return previous[:m.start()] + new.group().strip() + previous[m.start() + len(old):]


def calculator_in_scope(query, history):
    """The calculator a calculation question is about, by the same scopes tax_calculation uses."""
    stripped = PENALTY_WORD.sub("", query)
    for text in (query, stripped):
        for scope, tool in ((retirement_scope, "retirement"), (income_tax_scope, "income_tax"),
                            (virtual_asset_scope, "income_tax"), (capital_gains_scope, "capital_gains"),
                            (gift_scope, "gift"), (inheritance_scope, "inheritance"), (vat_scope, "vat")):
            if scope(text, history):
                return tool
    return "penalty_tax" if penalty_scope(query, history) else None


def ask_calculator_facts(tool):
    title, facts = CALCULATOR_FACTS[tool]
    return ToolRun(tool, "needs_input",
                   f"말씀하신 내용만으로는 {title} 계산기 입력을 확정하지 못했습니다. 다음 사실을 '항목 금액' 형태로 알려주세요: "
                   f"{facts}. 감면·특례처럼 채팅에서 읽지 못하는 조건은 계산기 화면의 "
                   + ("해당 세목 탭 가산세 옵션에서" if tool == "penalty_tax" else f"{title} 탭에서") + " 직접 입력할 수 있습니다.",
                   error_code="calculation_inputs_required")


async def tax_calculation(query, history, on_event=None, facts_query=None):
    """The six tax calculators in order; facts_query is the question the penalty option is read from."""
    facts = facts_query or query
    if retirement_scope(query, history):
        # 퇴직소득은 종합소득과 따로 과세하므로 종합소득세 해석보다 먼저 본다.
        result = await retirement_calculation(query, history, on_event, facts)
        if result is not None:
            return result
    if income_tax_scope(query, history):
        # The deterministic calculator answers when the amounts can be read; for financial
        # income the model's free-form formula is the fallback, not the first choice.
        result = await income_calculation(query, history, on_event, facts)
        if result is not None:
            return result
        if financial_income_scope(query, history):
            return ToolRun("formula_calculation", "planned", "공식 근거를 확인한 산식으로 참고 계산을 준비합니다.")
    if virtual_asset_scope(query, history):
        # 가상자산은 양도소득이 아니라 기타소득 분리과세라 양도소득세 해석보다 먼저 본다.
        result = await virtual_asset_calculation(query, history, on_event, facts)
        if result is not None:
            return result
    for scope, run in ((capital_gains_scope, capital_gains_calculation), (gift_scope, gift_calculation),
                       (inheritance_scope, inheritance_calculation), (vat_scope, vat_calculation)):
        if scope(query, history):
            result = await run(query, history, on_event, facts)
            if result is not None:
                return result
    return None


def _with_penalty(stated, facts_query, history):
    """Add the penalty option a tax question states; MissingInputs when its deciding facts are absent."""
    from app.services.calculator.penalty_inputs import stated_penalty_option
    if stated is None or hasattr(stated, "labels") or facts_query is None:
        return stated
    option = stated_penalty_option(facts_query, history)
    if option is None or hasattr(option, "labels"):
        return option or stated
    return replace(stated, params={**stated.params, **option.params},
                   assumptions=[*stated.assumptions, *option.assumptions])


async def _stated_calculation(tool, title, stated, on_event):
    """Run a calculator on inputs read from the question; None when it cannot be used.

    `stated` is a reader's StatedInputs, its MissingInputs (facts that decide the tax and are
    asked, never guessed), or None (a case the reader leaves to another path).
    """
    from app.services.calculator.engine import run_calculation
    from app.services.calculator.errors import CalculationError
    if stated is None:
        return None
    if hasattr(stated, "labels"):
        result = ToolRun(tool, "needs_input", f"{title}를 계산하려면 다음 사실을 알려주세요: " + ", ".join(stated.labels) + ".",
                         error_code="calculation_inputs_required")
        _emit_result(result, {}, on_event)
        return result
    try:
        if on_event:
            on_event({"type": "tool", "id": "primary", "tool": tool, "status": "running"})
        run = await run_calculation(tool, stated.params)
    except (CalculationError, ValueError, KeyError, TypeError) as exc:
        logger.info("%s calculator not used (%s)", tool, type(exc).__name__)
        return None
    # Assumptions lead the result: they change the amounts as much as the inputs do.
    run.context = "\n".join(["계산에 쓴 가정:", *[f"- {item}" for item in stated.assumptions], "", run.context])
    result = ToolRun(tool, "ok", "", run)
    _emit_result(result, stated.params, on_event)
    return result


async def income_calculation(query, history, on_event=None, facts_query=None):
    """종합소득세 계산기 결과, a request for the facts it must not assume, or None for another path."""
    from app.services.calculator.errors import CalculationError
    from app.services.calculator.income_tax_inputs import stated_income_tax_inputs
    from app.services.calculator.repository import get_deduction
    try:
        row = await get_deduction("소득세", "기본공제")
    except CalculationError as exc:
        logger.info("Income tax calculator not used (%s)", exc.code)
        return None
    stated = stated_income_tax_inputs(query, history, basic_deduction=int(row["amount"]))
    return await _stated_calculation("income_tax", "종합소득세", _with_penalty(stated, facts_query, history), on_event)


async def capital_gains_calculation(query, history, on_event=None, facts_query=None):
    """양도소득세 계산기 결과, a request for the facts it must not assume, or None for the model path."""
    from app.services.calculator.capital_gains_inputs import stated_capital_gains_inputs
    return await _stated_calculation("capital_gains", "양도소득세", _with_penalty(stated_capital_gains_inputs(query, history), facts_query, history), on_event)


async def gift_calculation(query, history, on_event=None, facts_query=None):
    """증여세 계산기 결과, a request for the facts it must not assume, or None for the model path."""
    from app.services.calculator.gift_inputs import stated_gift_inputs
    return await _stated_calculation("gift", "증여세", _with_penalty(stated_gift_inputs(query, history), facts_query, history), on_event)


async def inheritance_calculation(query, history, on_event=None, facts_query=None):
    """상속세 계산기 결과, a request for the facts it must not assume, or None for the model path."""
    from app.services.calculator.inheritance_inputs import stated_inheritance_inputs
    return await _stated_calculation("inheritance", "상속세", _with_penalty(stated_inheritance_inputs(query, history), facts_query, history), on_event)


async def vat_calculation(query, history, on_event=None, facts_query=None):
    """부가가치세 계산기 결과, a request for the facts it must not assume, or None for the model path."""
    from app.services.calculator.vat_inputs import stated_vat_inputs
    return await _stated_calculation("vat", "부가가치세", _with_penalty(stated_vat_inputs(query, history), facts_query, history), on_event)


async def penalty_calculation(query, history, on_event=None):
    """본세를 말한 가산세 질문의 결과, a request for the facts it must not assume, or None for another path."""
    from app.services.calculator.penalty_inputs import stated_penalty_inputs
    return await _stated_calculation("penalty_tax", "가산세", stated_penalty_inputs(query, history), on_event)


async def retirement_calculation(query, history, on_event=None, facts_query=None):
    """퇴직소득세 계산기 결과, a request for the facts it must not assume, or None for the model path."""
    from app.services.calculator.retirement_inputs import stated_retirement_inputs
    return await _stated_calculation("retirement", "퇴직소득세", _with_penalty(stated_retirement_inputs(query, history), facts_query, history), on_event)


async def virtual_asset_calculation(query, history, on_event=None, facts_query=None):
    """가상자산소득(종합소득세 계산기의 분리과세 항목) 결과, a request for missing facts, or None."""
    from app.services.calculator.virtual_asset_inputs import stated_virtual_asset_inputs
    stated = _with_penalty(stated_virtual_asset_inputs(query, history), facts_query, history)
    return await _stated_calculation("income_tax", "가상자산 소득세", stated, on_event)


def _emit_result(result, params, callback):
    if callback:
        callback({
            "type": "tool", "id": "primary", "tool": result.tool,
            "status": result.status,
            "error_code": result.error_code, "retryable": result.retryable,
            "params": result.calculation.params if result.calculation else params,
            "context": result.calculation.context if result.calculation else result.context,
        })

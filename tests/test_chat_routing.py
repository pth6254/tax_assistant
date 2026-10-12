"""Chat routing found in the 2026-10-12 structure check (no model call)."""
import json
import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services import chat_service as chat
from app.services import reliable_workflow as reliable
from app.services.calculator.engine import CalcRun, format_calculation_context
from app.services.calculator.tax_date import stated_tax_date
from app.services.chat_history import history_entry
from app.services.evidence import context_from_records
from app.services.tools import planner

QUESTION = "1세대 1주택 아파트 15억에 매도, 취득가 5억, 보유 10년이면 양도세 얼마야?"
ASKED = {"role": "assistant", "content": "거주기간을 알려주세요.", "calculator_request": "capital_gains"}


def test_the_stored_tool_status_marks_a_calculator_question():
    stored = {"role": "assistant", "content": "…", "tools": [
        {"tool": "capital_gains", "status": "needs_input", "error_code": "calculation_inputs_required"}]}
    assert history_entry(json.dumps(stored, ensure_ascii=False))["calculator_request"] == "capital_gains"
    issue = {"role": "assistant", "content": "…", "tools": [
        {"tool": "gift", "status": "needs_input", "error_code": "calculation_inputs_required", "scope": "issue"}]}
    assert "calculator_request" not in history_entry(issue)


@pytest.fixture
def asked(monkeypatch):
    seen = []

    async def calculation(query, history, on_event=None, facts_query=None):
        seen.append((query, history))

    monkeypatch.setattr(planner, "tax_calculation", calculation)
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no selection")))
    return seen


@pytest.mark.asyncio
async def test_a_reply_to_the_calculator_continues_its_calculation(asked):
    await planner.run_tools_for_query("거주 10년이야", user_id=str(uuid.uuid4()),
                                      history=[{"role": "user", "content": QUESTION}, ASKED])
    query, history = asked[0]
    assert query == QUESTION + "\n거주 10년이야" and history == []


@pytest.mark.asyncio
async def test_replies_to_several_questions_in_a_row_are_joined(asked):
    history = [{"role": "user", "content": QUESTION}, ASKED, {"role": "user", "content": "거주 1년"},
               {"role": "assistant", "content": "조정대상지역?", "calculator_request": "capital_gains"}]
    await planner.run_tools_for_query("비조정지역이야", user_id=str(uuid.uuid4()), history=history)
    assert asked[0][0] == QUESTION + "\n거주 1년\n비조정지역이야"


@pytest.mark.asyncio
async def test_a_new_question_leaves_the_pending_calculation(asked):
    result = await planner.run_tools_for_query("비과세 요건이 뭐야?", user_id=str(uuid.uuid4()),
                                               history=[{"role": "user", "content": QUESTION}, ASKED])
    assert result is None and not asked


def test_a_question_for_facts_is_not_reported_as_a_failure():
    events = [{"type": "tool", "tool": "gift", "status": "needs_input", "context": "증여세를 계산하려면 …"}]
    answer = chat._failed_tool_answer(events)
    assert "이어서 계산" in answer and "계산 실패" not in answer


@pytest.mark.parametrize("tool, text, expected", [
    ("income_tax", "2023년 귀속 종합소득세 계산해줘. 연봉 5천만원", date(2023, 12, 31)),
    ("capital_gains", "2020년에 산 아파트를 2024년 3월 5일에 10억에 팔았어", date(2024, 3, 5)),
    ("capital_gains", "2020년에 산 아파트를 10억에 팔면 양도세 얼마야?", None),
    ("gift", "증여일은 2025-05-01이고 아들에게 3억", date(2025, 5, 1)),
    ("vat", "2025년 1기 매출 1억", date(2025, 6, 30)),
    ("income_tax", "연봉 5천만원이면 소득세 얼마야?", None),
])
def test_the_taxed_event_date_sets_the_law(tool, text, expected):
    found = stated_tax_date(tool, [text])
    assert (found[0] if found else None) == expected


def test_two_dates_for_one_event_are_asked():
    assert stated_tax_date("capital_gains", ["2023년에 팔았나 2024년에 팔았나"])[0] == "ambiguous"


def test_the_result_names_the_law_date():
    result = CalculationResult(tax_type="증여세", steps=[TaxStep(label="납부할 세액", amount=1)], taxable_income=1,
                               calculated_tax=1, final_tax=1, effective_rate=0.1, source_articles=[],
                               basis=TaxBasis(queried_on="2023-12-31", effective_dates=[]))
    assert "적용 세법 기준일: 2023-12-31" in format_calculation_context(result)


@pytest.mark.asyncio
async def test_an_issue_that_names_its_tax_runs_without_the_other_issues(monkeypatch):
    from app.schemas.reliability import Issue, QuestionPlan
    query = "연봉 5천만원이면 소득세 얼마인지 계산하고, 아파트 양도세도 계산해줘"
    plan = QuestionPlan(issues=[Issue(id="C1", kind="calculation", law="소득세법",
                                      request_quote="연봉 5천만원이면 소득세 얼마인지 계산하고", question="소득세"),
                                Issue(id="C2", kind="calculation", law="소득세법", request_quote="계산해줘",
                                      question="양도세")])
    monkeypatch.setattr(reliable, "plan_question", AsyncMock(return_value=plan))
    monkeypatch.setattr(reliable, "retrieve_issues", AsyncMock(return_value=context_from_records([], plan=plan)))
    monkeypatch.setattr(reliable, "attach_event_versions", AsyncMock(side_effect=lambda c: c))
    run = AsyncMock(return_value=None)
    monkeypatch.setattr(reliable, "run_tools_for_query", run)
    await reliable.prepare_context(query, [], "u", [], AsyncMock())
    histories = [call.kwargs["history"] for call in run.await_args_list]
    assert histories[0] == [] and histories[1][-1]["content"] == query


@pytest.mark.asyncio
async def test_a_streamed_reference_formula_is_saved(monkeypatch):
    calc = CalcRun("검증된 예시 계산", "formula_calculation", {}, verification={"status": "limited"})
    monkeypatch.setattr(chat, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_fetch_rag_and_web_context",
                        AsyncMock(return_value=(context_from_records([]), "웹 검색 생략", [], calc)))
    saved = AsyncMock()
    monkeypatch.setattr(chat, "_save_history", saved)
    events = [e async for e in chat._stream_chat_response_impl("해외 아파트 양도세 얼마야?", str(uuid.uuid4()), "u")]
    assert [e["type"] for e in events][-2:] == ["chunk", "verification"]
    saved.assert_awaited_once()


def test_a_past_tense_amount_question_is_a_calculation():
    assert planner.has_calculation_intent("2010년 귀속 연봉 5천만원 소득세 얼마였어?")


@pytest.mark.asyncio
async def test_a_date_before_the_stored_tables_is_reported_not_replaced_by_today(monkeypatch):
    from app.services.calculator import engine
    from app.services.calculator.errors import CalculationError
    from app.services.calculator.income_tax_inputs import StatedInputs

    async def missing(tool, params):
        raise CalculationError("missing_tax_data")

    monkeypatch.setattr(engine, "run_calculation", missing)
    stated = StatedInputs({"wage_income": 50_000_000}, [])
    result = await planner._stated_calculation("income_tax", "종합소득세", stated, None,
                                               texts=["2010년 귀속 연봉 5천만원 소득세 얼마였어?"])
    assert result.error_code == "tax_date_unavailable" and "2010-12-31" in result.context


def test_a_calculator_answer_is_a_conclusion_then_a_table():
    from app.services.calculator.engine import format_calculation_answer
    result = CalculationResult(tax_type="증여세", steps=[TaxStep(label="증여재산가액", amount=300_000_000),
                                                       TaxStep(label="공제(직계|성인)", amount=50_000_000),
                                                       TaxStep(label="납부할 세액", amount=38_800_000)],
                               taxable_income=250_000_000, calculated_tax=40_000_000, final_tax=38_800_000,
                               effective_rate=0.129, source_articles=["상속세 및 증여세법 제53조"], notes=["참고 사항"],
                               basis=TaxBasis(queried_on="2026-10-12", effective_dates=[]))
    answer = format_calculation_answer(CalcRun("ctx", "gift", {}, result=result, assumptions=("성인으로 보았습니다.",)))
    lines = answer.splitlines()
    assert lines[0] == "말씀하신 조건에서 **증여세 납부할 세액은 38,800,000원**으로 계산됩니다."
    assert "| 항목 | 금액 |" in lines and "| 증여재산가액 | 300,000,000원 |" in lines
    assert r"| 공제(직계\|성인) | 50,000,000원 |" in lines
    assert "- 성인으로 보았습니다." in lines and "- 적용 세법 기준일: 2026-10-12" in lines
    refund = result.model_copy(update={"final_tax": -1_000_000, "tax_type": "부가가치세"})
    assert "환급받을 세액은 1,000,000원" in format_calculation_answer(CalcRun("ctx", "vat", {}, result=refund))

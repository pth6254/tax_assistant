"""A calculation chat answers from what the conversation says: facts read and proven, cases computed when a
deciding fact is open, and a question for an amount explained instead of asked alone (no model call)."""
import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.services import chat_service as chat
from app.services.calculator import capital_gains as cg
from app.services.calculator import fact_reading as fr
from app.services.calculator import inheritance as ih
from app.services.calculator.engine import format_calculation_answer
from app.services.calculator.fact_reading import ReadFact, ReadFacts
from app.services.chat_history import history_entry
from app.services.evidence import EvidenceContext
from app.services.tools import planner
from tests.test_capital_gains import params as cg_params
from tests.test_inheritance import params as ih_params

USER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def stored_figures(monkeypatch):
    async def cg_load(as_of=None):
        return cg_params()

    async def ih_load(as_of=None):
        return ih_params()
    monkeypatch.setattr(cg, "load_parameters", cg_load)
    monkeypatch.setattr(ih, "load_parameters", ih_load)
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no tool selection")))


@pytest.fixture
def model(monkeypatch):
    """The model's fact list for the next reading; each call is recorded."""
    calls = []

    def answer(tool, *rows):
        async def read_facts(query, history, **kwargs):
            calls.append((query, history, kwargs))
            return ReadFacts(tool=tool, facts=[ReadFact(field=f, value=v, quote=q) for f, v, q in rows])
        monkeypatch.setattr(fr, "read_facts", read_facts)
    answer.calls = calls
    return answer


def asked_reply(tool, labels):
    """A stored calculator question, as the next turn's history sees it."""
    return history_entry({"role": "assistant", "content": "…", "tools": [
        {"tool": tool, "status": "needs_input", "error_code": "calculation_inputs_required", "asked": labels}]})


@pytest.mark.asyncio
async def test_the_real_banpo_conversation_is_answered_without_asking_about_the_area(model):
    model("capital_gains",
          ("transfer_price", "1200000000", "12억에 팔고"), ("acquisition_price", "700000000", "취득가는 7억"),
          ("holding_years", "10", "10년 보유한"), ("is_one_home", "true", "1세대 1주택이야"),
          ("acquisition_date", "2014", "2014년 매입해서"), ("residence_end", "2019", "2019년까지 거주"))
    history = [{"role": "user", "content": "10년 보유한 아파트를 12억에 팔고 취득가는 7억이면 양도세 계산해줘"},
               asked_reply("capital_gains", ["1세대 1주택 여부(양도일 현재 세대가 가진 주택 수)"]),
               {"role": "user", "content": "1세대 1주택이야"}, asked_reply("capital_gains", ["보유기간 중 거주기간"])]
    run = await planner.run_tools_for_query("2014년 매입해서 2019년까지 거주하다가 지금까지 전세주고 있어",
                                            user_id=USER, history=history)
    assert run.status == "ok" and run.calculation.result.final_tax == 0
    assert run.calculation.params["residence_years"] in (4, 5)
    assert run.calculation.params["acquired_in_adjusted_area"] is False
    assert not run.calculation.scenarios   # both readings of the years give 0원
    text = " ".join(run.calculation.assumptions)
    assert "2017년 8월 2일 이전" in text and "어느 경우든 세액이 같습니다" in text
    # The model saw the conversation as written, with the calculator's last question.
    query, seen, kwargs = model.calls[0]
    assert query.startswith("2014년") and kwargs["asked"] == ["보유기간 중 거주기간"]


@pytest.mark.asyncio
async def test_an_open_deciding_fact_is_answered_by_cases_and_then_asked(model):
    question = "1주택자고 2022년 2월에 6억에 사서 2026년 11월에 8억에 팔 예정이야. 18개월 살았어. 양도세 얼마야?"
    model("capital_gains", ("transfer_price", "800000000", "8억에 팔 예정"), ("acquisition_price", "600000000", "6억에 사서"),
          ("acquisition_date", "2022-02", "2022년 2월에 6억에 사서"), ("transfer_date", "2026-11", "2026년 11월에 8억에 팔"),
          ("residence_months", "18", "18개월 살았어"), ("is_one_home", "true", "1주택자고"))
    events = []
    run = await planner.run_tools_for_query(question, user_id=USER, history=[], on_event=events.append)
    cases = run.calculation.scenarios
    assert run.status == "ok" and [c.label for c in cases] == ["취득 당시 조정대상지역이었다면", "취득 당시 조정대상지역이 아니었다면"]
    assert cases[0].calculation.result.final_tax > 0 and cases[1].calculation.result.final_tax == 0
    assert all(c.calculation.params["holding_years"] == 4 and c.calculation.params["residence_years"] == 1 for c in cases)
    answer = format_calculation_answer(run.calculation)
    assert "경우별로 계산했습니다" in answer and "어느 경우인지 알려주시면" in answer
    # The stored reply keeps the question, so "네" next turn answers it.
    entry = history_entry({"role": "assistant", "content": answer, "tools": chat._terminal_tools(events)})
    assert entry["calculator_request"] == "capital_gains" and any("조정대상지역" in a for a in entry["calculator_asked"])


@pytest.mark.asyncio
async def test_an_inheritance_named_only_by_the_death_is_calculated(model):
    model("inheritance", ("estate_value", "5000000000", "50억을 받았어"), ("has_spouse", "false", "부모님이 돌아가셔서"))
    run = await planner.run_tools_for_query("부모님이 돌아가셔서 50억을 받았어 내가 내야하는 세금이 얼마야?",
                                            user_id=USER, history=[])
    assert run.status == "ok"
    assert run.calculation.params["estate_value"] == 5_000_000_000 and run.calculation.params["has_spouse"] is False
    # The number of children is open, but 1~3 children give the same tax without a spouse (일괄공제 5억원).
    assert not run.calculation.scenarios and any("어느 경우든" in a for a in run.calculation.assumptions)


@pytest.mark.asyncio
async def test_a_missing_amount_is_asked_with_what_was_understood_and_explained_first(model):
    model("capital_gains", ("transfer_price", "1000000000", "10억에 팔았는데"), ("asset_type", "주택", "아파트"))
    run = await planner.run_tools_for_query("아파트를 10억에 팔았는데 양도세 얼마야?", user_id=USER, history=[])
    assert run.status == "needs_input" and run.explain
    assert "취득가액" in " ".join(run.asked) and run.understood and "10억에 팔았는데" in run.context
    assert chat.needs_input_reply(run) == "explain_ask"


@pytest.mark.asyncio
async def test_without_the_model_the_readers_question_stands():
    run = await planner.run_tools_for_query("1주택인데 10억에 산 아파트를 15억에 팔면 양도세 얼마야? 7년 보유",
                                            user_id=USER, history=[])
    assert run.status == "needs_input" and any("거주기간" in a for a in run.asked) and run.explain


@pytest.mark.asyncio
async def test_a_complete_reading_does_not_call_the_model(model):
    model("capital_gains")
    run = await planner.run_tools_for_query(
        "10억에 산 아파트를 15억에 팔면 양도소득세 얼마야? 1세대 1주택이고 7년 보유, 5년 거주했어", user_id=USER, history=[])
    assert run.status == "ok" and model.calls == []


def test_an_amount_no_input_uses_means_the_reader_missed_it():
    texts = ["카페 하는데 이번 1기 매출이 6천만원이고 재료비랑 임대료로 세금계산서 받은 게 2천만원이야."]
    assert planner.unused_amounts(texts, {"sales": 60_000_000, "purchases": 0}) == ["2천만원"]
    assert planner.unused_amounts(texts, {"sales": 60_000_000, "purchases": 20_000_000}) == []


@pytest.mark.asyncio
async def test_the_first_question_for_an_amount_comes_with_an_explanation(monkeypatch):
    from app.services.tools.executor import ToolRun
    run = ToolRun("capital_gains", "needs_input", "정확한 양도소득세을(를) 계산하려면 다음 사실을 알려주세요: 취득가액.",
                  error_code="calculation_inputs_required", asked=("취득가액",), explain=True,
                  question="아파트를 10억에 팔았는데 양도세 얼마야?")

    async def tools(query, *, user_id, history, on_event=None):
        on_event({"type": "tool", "id": "primary", "tool": "capital_gains", "status": "needs_input",
                  "error_code": "calculation_inputs_required", "context": run.context, "asked": ["취득가액"]})
        return run
    monkeypatch.setattr(chat, "run_tools_for_query", tools)
    monkeypatch.setattr(chat, "prepare_context", AsyncMock(return_value=EvidenceContext("근거", ())))
    answer_with = AsyncMock(return_value=("1세대 1주택 비과세 요건은 …", {"status": "checked"}))
    monkeypatch.setattr(chat, "_answer_evidence_context", answer_with)
    turn = await chat._answer_turn("아파트를 10억에 팔았는데 양도세 얼마야?", __import__("uuid").uuid4(), USER,
                                   lambda event: None, history_override=[])
    assert not turn.failed and turn.answer.startswith("1세대 1주택 비과세 요건은")
    assert "정확한 세액 계산에 필요한 정보" in turn.answer and "취득가액" in turn.answer
    assert answer_with.call_args.args[0] == run.question
    assert history_entry({"role": "assistant", "content": turn.answer, "tools": chat._terminal_tools(turn.events)})[
        "calculator_request"] == "capital_gains"


def test_a_stored_case_answer_keeps_its_question():
    entry = history_entry(json.dumps({"role": "assistant", "content": "…", "tools": [
        {"tool": "gift", "status": "ok", "asked": ["주는 사람과 받는 사람의 관계"]}]}, ensure_ascii=False))
    assert entry["calculator_request"] == "gift" and entry["calculator_asked"] == ["주는 사람과 받는 사람의 관계"]
    assert "calculator_request" not in history_entry({"role": "assistant", "content": "…",
                                                      "tools": [{"tool": "gift", "status": "ok"}]})


def test_a_follow_up_may_say_what_the_new_amount_is_for():
    history = [{"role": "user", "content": "10년 보유·거주한 1세대 1주택 아파트를 15억에 팔았고 취득가는 5억이야. 양도세 얼마야?"},
               {"role": "assistant", "content": "…"}]
    assert planner.is_calculation_followup("그럼 18억에 팔면?", history)
    assert planner.is_calculation_followup("그럼 7억 5천이면?", history)
    assert not planner.is_calculation_followup("그럼 18억에 팔면 비과세 요건은?", history)


def test_cases_with_the_same_tax_share_a_row():
    from types import SimpleNamespace
    from app.services.calculator.engine import CalcRun
    from app.services.calculator.understanding import Case
    from app.schemas.calculator import CalculationResult, TaxStep

    def run(final):
        result = CalculationResult(tax_type="상속세", steps=[TaxStep(label="결정세액", amount=final)], taxable_income=0,
                                   calculated_tax=final, final_tax=final, effective_rate=0.1, source_articles=[])
        return CalcRun(context="", tool="inheritance", params={}, result=result)
    first = run(100)
    first.scenarios = (Case("배우자가 살아 있으면 · 자녀가 1명이면", first), Case("배우자가 살아 있으면 · 자녀가 3명이면", run(100)),
                       Case("배우자가 없으면 · 자녀가 1명이면", run(300)))
    answer = format_calculation_answer(first)
    assert "| 배우자가 살아 있으면 · 자녀가 1명이면 또는 자녀가 3명이면 | 100원 |" in answer
    assert "| 배우자가 없으면 · 자녀가 1명이면 | 300원 |" in answer


def test_a_date_in_the_next_sentence_is_not_the_sale_date():
    from datetime import date as day
    from app.services.calculator.tax_date import stated_tax_date
    text = "집이 두 채인데 그중 마포구 아파트를 2026년 10월에 12억에 팔았어. 2019년에 5억에 샀어. 양도세 얼마야?"
    assert stated_tax_date("capital_gains", [text])[0] == day(2026, 10, 31)
    assert stated_tax_date("capital_gains", ["양도일은 2024-05-01이야"])[0] == day(2024, 5, 1)

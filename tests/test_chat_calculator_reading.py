"""Chat questions that the calculator readers used to misread (2026-10-11 chat check, no model call)."""
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.services.calculator.capital_gains_inputs import MissingInputs, stated_capital_gains_inputs
from app.services.calculator.income_tax_inputs import stated_income_tax_inputs
from app.services.tools import planner


def test_spoken_holding_and_residence_periods_are_read():
    stated = stated_capital_gains_inputs("1세대 1주택 아파트 15억에 매도, 취득가 5억, 보유 10년 거주 10년이면 양도소득세 계산해줘")
    assert (stated.params["holding_years"], stated.params["residence_years"]) == (10, 10)
    assert stated.params["is_one_home"]
    land = stated_capital_gains_inputs("상가를 5억에 팔았어. 취득가 3억, 보유 5년. 양도세 얼마야?")
    assert land.params["holding_years"] == 5


def test_a_denied_single_home_is_not_read_as_one():
    stated = stated_capital_gains_inputs("아파트를 10억에 팔았고 5억에 샀어. 8년 보유했고 1세대 1주택이 아니야. 양도세 얼마야?")
    # 다주택 경로: 비과세 대신 조정대상지역 여부를 묻는다.
    assert isinstance(stated, MissingInputs) and any("조정대상지역" in label for label in stated.labels)
    stated = stated_capital_gains_inputs("아파트를 10억에 팔았고 5억에 샀어. 8년 보유, 1주택자가 아니고 비조정지역이야. 양도세 얼마야?")
    assert stated.params["is_one_home"] is False


def test_an_earlier_sale_in_the_same_year_is_asked_and_then_compared():
    asked = stated_capital_gains_inputs("올해 토지를 이미 하나 팔았고 이번에 토지를 3억에 팔아. 취득가 2억, 5년 보유. 양도세 계산해줘")
    assert isinstance(asked, MissingInputs) and "과세표준과 산출세액" in asked.labels[0]
    stated = stated_capital_gains_inputs("올해 토지를 이미 하나 팔았어(과세표준 5천만원, 산출세액 624만원). 이번에 토지를 3억에 팔아. "
                                         "취득가 2억, 5년 보유. 양도세 계산해줘")
    assert (stated.params["prior_same_year_taxable"], stated.params["prior_same_year_tax"]) == (50_000_000, 6_240_000)
    assert any("비교과세" in note for note in stated.assumptions)


def test_house_deposits_and_religious_income_are_read():
    deposits = stated_income_tax_inputs("주택 3채 임대 보증금 합계 6억원, 월세 수입 1천만원이면 종합소득세 얼마야?",
                                        basic_deduction=1_500_000)
    assert (deposits.params["rental_deposits"], deposits.params["rental_house_count"],
            deposits.params["rental_income"]) == (600_000_000, 3, 10_000_000)
    count = stated_income_tax_inputs("임대 보증금 6억원, 월세 수입 1천만원이면 종합소득세 얼마야?", basic_deduction=1_500_000)
    assert "임대하는 주택 수" in count.labels[0]
    religious = stated_income_tax_inputs("종교인소득 3천만원이면 소득세 얼마야?", basic_deduction=1_500_000)
    assert religious.params["religious_income"] == 30_000_000 and not religious.params["religious_as_wage"]
    wage = stated_income_tax_inputs("종교인소득 3천만원을 근로소득으로 신고하면 소득세 얼마야?", basic_deduction=1_500_000)
    assert wage.params["religious_as_wage"]


def test_a_spoken_month_count_sets_the_late_filing_period():
    from app.services.calculator.penalty_inputs import stated_penalty_option
    option = stated_penalty_option("상가를 5억에 팔았는데 신고를 안 했어. 기한 지나고 한 달 안에 신고할 거야. 가산세 얼마야?", [])
    assert option.params["penalty_type"] == "무신고" and option.params["filed_within_months"] == 1


@pytest.mark.parametrize("query, intended", [
    ("성인 자녀에게 3억 증여했는데 신고를 안 했어. 증여세 가산세 포함 얼마야?", True),
    ("가산세까지 합치면 얼마야?", True),
    ("증여세 공제 한도는 얼마야?", False),
])
def test_a_total_with_the_penalty_is_a_calculation_request(query, intended):
    assert planner.has_calculation_intent(query) is intended


@pytest.mark.asyncio
async def test_calculator_questions_never_pay_for_a_selection(monkeypatch):
    select = AsyncMock(side_effect=AssertionError("no selection for the six calculators"))
    monkeypatch.setattr(planner, "select_tool", select)
    result = await planner.run_tools_for_query("양도소득세 계산해줘", user_id=str(uuid4()))
    assert (result.tool, result.status) == ("capital_gains", "needs_input")
    assert "양도가액" in result.context and "transfer_price" not in result.context

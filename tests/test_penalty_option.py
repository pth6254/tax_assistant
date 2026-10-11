"""The six tax calculators carry the penalty (가산세) as an option, and virtual assets are a separately taxed
item of the income tax calculator. The penalty figures follow 국세기본법 제47조의2~제48조 as in
tests/test_vat_penalty.py; the tax before the penalty is each calculator's own verified result."""
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import capital_gains as cg, gift_tax as gt, penalty_tax as pt, vat, virtual_asset as va
from app.services.calculator import financial_income_tax, income_tax
from app.services.calculator.errors import CalculationError
from app.services.calculator.penalty_inputs import MissingInputs, StatedInputs, stated_penalty_option
from app.services.tools import planner
from tests.test_calculator import _patch_repository
from tests.test_capital_gains import params as cg_params
from tests.test_gift_tax import params as gift_params
from tests.test_vat_penalty import penalty_params, vat_params
from tests.test_virtual_asset import params as va_params


@pytest.fixture
def stored_figures(monkeypatch):
    async def gift(as_of=None):
        return gift_params()

    async def capital(as_of=None):
        return cg_params()

    async def penalty(as_of=None):
        return penalty_params()

    async def value_added(as_of=None):
        return vat_params()

    monkeypatch.setattr(gt, "load_parameters", gift)
    monkeypatch.setattr(cg, "load_parameters", capital)
    monkeypatch.setattr(pt, "load_parameters", penalty)
    monkeypatch.setattr(vat, "load_parameters", value_added)


def step(result, prefix):
    found = [s.amount for s in result.steps if s.label.startswith(prefix)]
    assert len(found) == 1, (prefix, [s.label for s in result.steps])
    return found[0]


@pytest.mark.asyncio
async def test_no_return_drops_the_filing_credit_and_adds_the_penalty(stored_figures):
    on_time = await gt.calculate(gift_amount=300_000_000, relation="직계존비속")
    late = await gt.calculate(gift_amount=300_000_000, relation="직계존비속", penalty_type="무신고",
                              filed_within_months=1, days_late=30)
    assert on_time.final_tax == 38_800_000
    # 신고세액공제 없이 4천만 + 무신고 20% 800만의 기한 후 신고 50% 감면 400만 + 30일 x 0.022% 264,000
    assert step(late, "가산세 대상 세액") == 40_000_000
    assert step(late, "가산세 합계") == 4_264_000 and late.final_tax == 44_264_000
    assert late.notes[0].startswith("무신고(기한 후 신고 포함)에는 신고세액공제가 없어")


@pytest.mark.asyncio
async def test_under_reporting_charges_only_the_shortfall(stored_figures):
    result = await cg.calculate(transfer_price=1_500_000_000, acquisition_price=1_000_000_000, holding_years=7,
                                is_one_home=True, residence_years=5, penalty_type="과소신고", reported_tax=5_000_000)
    assert step(result, "가산세 대상 세액(바른 납부할 세액 6,165,000원 - 신고한 세액 5,000,000원)") == 1_165_000
    assert step(result, "과소신고가산세") == 116_500
    assert result.final_tax == 1_165_000 + 116_500


@pytest.mark.asyncio
async def test_late_payment_counts_only_the_unpaid_tax(stored_figures):
    result = await vat.calculate(sales=100_000_000, purchases=60_000_000, penalty_type="납부지연",
                                 reported_tax=3_000_000, days_late=100)
    # 납부세액 400만 - 이미 낸 300만 = 100만 x 0.022% x 100일
    assert step(result, "미납세액") == 1_000_000 and step(result, "납부지연가산세") == 22_000
    assert result.final_tax == 1_022_000


@pytest.mark.asyncio
async def test_no_vat_return_has_no_e_filing_credit(stored_figures):
    result = await vat.calculate(sales=100_000_000, purchases=60_000_000, e_filing=True, penalty_type="무신고")
    assert not [s for s in result.steps if s.label == "전자신고세액공제"]
    assert step(result, "가산세 대상 세액") == 4_000_000


@pytest.mark.asyncio
@pytest.mark.parametrize("option", [{"days_late": 10}, {"penalty_type": "무신고", "reported_tax": 1},
                                    {"penalty_type": "납부지연", "penalty_revenue": 1}])
async def test_inconsistent_penalty_options_are_rejected(stored_figures, option):
    with pytest.raises(CalculationError):
        await gt.calculate(gift_amount=300_000_000, relation="직계존비속", **option)


@pytest.mark.asyncio
async def test_virtual_assets_are_added_to_the_income_tax_decided_tax(monkeypatch):
    async def load(as_of=None):
        return va_params(), True
    monkeypatch.setattr(va, "load_parameters", load)
    with _patch_repository(income_tax), _patch_repository(financial_income_tax):
        wage = await income_tax.calculate(income=50_000_000)
        both = await income_tax.calculate(income=50_000_000, virtual_transfer_price=50_000_000,
                                          virtual_acquisition_price=10_000_000)
    only = await income_tax.calculate(virtual_transfer_price=50_000_000, virtual_acquisition_price=10_000_000)
    # (5천만 - 1천만 - 250만) x 20% = 750만, 다른 소득과 합산하지 않고 결정세액에 더함
    assert both.final_tax == wage.final_tax + 7_500_000
    assert step(both, "가상자산소득 분리과세 세액") == 7_500_000
    assert only.final_tax == 7_500_000 and step(only, "가상자산 과세표준") == 37_500_000


@pytest.mark.asyncio
async def test_virtual_assets_sold_before_2027_are_not_taxed(monkeypatch):
    async def load(as_of=None):
        return va_params(), False
    monkeypatch.setattr(va, "load_parameters", load)
    result = await income_tax.calculate(virtual_transfer_price=50_000_000, virtual_acquisition_price=10_000_000,
                                        as_of=date(2026, 10, 11))
    assert result.final_tax == 0 and step(result, "가상자산 같은 조건으로 2027년 이후") == 7_500_000


@pytest.mark.parametrize("query, expected", [
    ("양도세 얼마야? 신고를 안 했고 기한이 2개월 지났어",
     {"penalty_type": "무신고", "filed_within_months": 2, "days_late": 60, "reported_tax": 0}),
    ("수정신고 하려고. 처음 신고한 세액 300만원이고 3개월 지났어",
     {"penalty_type": "과소신고", "reported_tax": 3_000_000, "filed_within_months": 3}),
    ("신고는 했는데 납부를 40일 늦게 했어", {"penalty_type": "납부지연", "days_late": 40, "reported_tax": 0}),
])
def test_penalty_facts_in_a_tax_question_are_read(query, expected):
    stated = stated_penalty_option(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params[k] for k in expected} == expected


def test_penalty_option_asks_for_deciding_facts_and_ignores_ordinary_questions():
    assert stated_penalty_option("아파트 15억에 팔면 양도세 얼마야?") is None
    assert isinstance(stated_penalty_option("가산세 포함해서 양도세 얼마야?"), MissingInputs)
    assert isinstance(stated_penalty_option("덜 신고했어, 1개월 지났어"), MissingInputs)   # 처음 신고한 세액


@pytest.mark.asyncio
async def test_chat_runs_the_tax_calculator_with_the_penalty_option(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no selection needed")))
    result = await planner.run_tools_for_query(
        "10억에 산 아파트를 15억에 팔았어. 1세대 1주택이고 7년 보유, 5년 거주했어. 신고를 안 했고 기한이 2개월 "
        "지났어. 가산세 포함해서 양도소득세 얼마야?", user_id=str(uuid4()))
    assert (result.tool, result.status) == ("capital_gains", "ok")
    context = result.calculation.context
    # 6,165,000 + 무신고 20%의 기한 후 신고(3개월 이내 30%) 감면 후 863,100 + 60일 x 0.022% 81,378
    assert "- 가산세 합계: 944,478원" in context and "- 납부할 총액(본세+가산세): 7,109,478원" in context
    assert "기한 후 신고하는 것으로 보아 감면을 적용했습니다" in context


@pytest.mark.asyncio
async def test_chat_reads_coin_sales_into_the_income_tax_calculator(monkeypatch):
    async def load(as_of=None):
        return va_params(), False
    monkeypatch.setattr(va, "load_parameters", load)
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no selection needed")))
    result = await planner.run_tools_for_query("비트코인을 1천만원에 사서 5천만원에 팔면 세금 얼마?", user_id=str(uuid4()))
    assert (result.tool, result.status) == ("income_tax", "ok")
    assert result.calculation.params["virtual_transfer_price"] == 50_000_000
    assert "가상자산 같은 조건으로 2027년 이후 양도하면 낼 세액(20%): 7,500,000원" in result.calculation.context

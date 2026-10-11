"""The finishing options of the six calculators, checked against the statute's formula by hand:
퇴직소득 연금계좌 과세이연(소득세법 제146조 제2항·시행령 제202조의2·제129조 제1항 제5호의3), 조합원입주권 1주택 비과세
(제89조 제1항 제4호·시행령 제160조), 같은 해 여러 건 양도 비교과세(제104조 제5항), 주택 보증금 간주임대료(제25조·
시행령 제53조·시행규칙 제23조), 종교인소득 필요경비(시행령 제87조 제3호), 영세율과세표준 신고불성실가산세(국세기본법
제47조의2 제2항·제47조의3 제2항), 과소신고의 신고세액공제(상속세 및 증여세법 시행령 제65조의2)."""
from dataclasses import replace
from decimal import Decimal

import pytest

from app.services.calculator import capital_gains as cg, gift_tax as gt, income_tax as it, penalty_tax as pt
from app.services.calculator import retirement as rt, vat
from app.services.calculator.errors import CalculationError
from tests.test_capital_gains import params as cg_params
from tests.test_gift_tax import params as gift_params
from tests.test_income_tax import params as income_params
from tests.test_retirement import params as retirement_params
from tests.test_vat_penalty import penalty_params, vat_params

PENSION_BANDS = [[10, "0.7"], [20, "0.6"], [None, "0.5"]]
DEEMED = {"amount": 300_000_000, "rate": Decimal("0.031"),
          "condition": {"ratio": "0.6", "house_count": 3, "two_house_deposit": 1_200_000_000}}
RELIGIOUS = [[20_000_000, "0.8", 0, 0], [40_000_000, "0.5", 16_000_000, 20_000_000],
             [60_000_000, "0.3", 26_000_000, 40_000_000], [None, "0.2", 32_000_000, 60_000_000]]


def step(steps, prefix):
    found = [amount for label, amount in steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, steps)
    return found[0]


def test_moving_retirement_pay_to_a_pension_account_defers_its_share_of_the_tax():
    full = rt.compute(params=retirement_params(), retirement_pay=100_000_000, service_years=20,
                      pension_transfer=100_000_000, pension_bands=PENSION_BANDS)
    # 산출세액 1,120,000원 전부 이연, 연금으로 받으면 10년 이하분 70% = 784,000원
    assert step(full.steps, "연금계좌 이체로 미뤄지는") == 1_120_000 and step(full.steps, "차감 납부할 세액") == 0
    assert step(full.steps, "연금으로 받을 때 낼 세금") == 784_000
    half = rt.compute(params=retirement_params(), retirement_pay=100_000_000, service_years=20,
                      pension_transfer=50_000_000, pension_bands=PENSION_BANDS)
    assert step(half.steps, "차감 납부할 세액") == 560_000 and step(half.steps, "지방소득세") == 56_000
    with pytest.raises(CalculationError):
        rt.compute(params=retirement_params(), retirement_pay=1, service_years=1, pension_transfer=2)


def test_a_single_membership_right_of_an_original_member_is_exempt_up_to_the_high_price_line():
    small = cg.compute(params=cg_params(), transfer_price=1_000_000_000, acquisition_price=500_000_000, holding_years=8,
                       asset_type="조합원입주권", is_one_home=True, residence_years=5, pre_approval_gain=400_000_000,
                       pre_approval_years=5)
    assert small.calculated_tax == 0 and small.method == "exempt"
    large = cg.compute(params=cg_params(), transfer_price=1_500_000_000, acquisition_price=500_000_000, holding_years=8,
                       asset_type="조합원입주권", is_one_home=True, residence_years=5, pre_approval_gain=400_000_000,
                       pre_approval_years=5)
    # 차익 10억 x 3/15 = 2억, 인가 전 차익 4억 x 표2 40%(보유 20%+거주 20%) x 3/15 = 3,200만
    # 소득금액 1억6,800만 - 250만 = 1억6,550만 x 38% - 1,994만 = 4,295만
    assert step(large.steps, "고가주택 과세대상 양도차익") == 200_000_000
    assert step(large.steps, "장기보유특별공제") == 32_000_000
    assert large.taxable_income == 165_500_000 and large.calculated_tax == 42_950_000
    unmet = cg.compute(params=cg_params(), transfer_price=1_000_000_000, acquisition_price=500_000_000, holding_years=8,
                       asset_type="조합원입주권", is_one_home=True, pre_approval_gain=400_000_000, pre_approval_years=1)
    assert unmet.calculated_tax > 0 and any("1조합원입주권이지만 비과세 요건" in n for n in unmet.notes)


@pytest.mark.parametrize("holding_years, expected", [
    # 토지 1억 차익, 5년 보유 공제 10% → 과세표준 9천만(기본공제는 앞선 양도에서 받음)
    # ① (9천만+5천만) x 35% - 1,544만 = 3,356만 ② 1,606만 + 624만 = 2,230만 → 3,356만 - 624만
    (5, 27_320_000),
    # 1년 보유 40%: ① 3,706만 ② 4,000만 + 624만 = 4,624만 → 4,624만 - 624만
    (1, 40_000_000),
])
def test_several_sales_in_a_year_take_the_larger_of_the_combined_and_separate_taxes(holding_years, expected):
    result = cg.compute(params=cg_params(), transfer_price=300_000_000, acquisition_price=200_000_000,
                        holding_years=holding_years, asset_type="토지·건물", prior_same_year_taxable=50_000_000,
                        prior_same_year_tax=6_240_000)
    assert step(result.steps, "양도소득 기본공제") == 0
    assert result.calculated_tax == expected


def test_securities_cannot_join_the_real_estate_comparison():
    with pytest.raises(CalculationError):
        cg.compute(params=cg_params(), transfer_price=2, acquisition_price=1, asset_type="주식", prior_same_year_tax=1)


@pytest.mark.parametrize("houses, deposits, two_house_rule, expected", [
    (3, 600_000_000, True, 5_580_000),      # (6억 - 3억) x 60% x 3.1%
    (2, 1_000_000_000, True, None),         # 2주택은 12억원 초과일 때만
    (2, 1_300_000_000, True, 18_600_000),   # (13억 - 3억) x 60% x 3.1%
    (2, 1_300_000_000, False, None),        # 2026년 과세기간 전
])
def test_house_deposits_add_deemed_rent_only_above_the_thresholds(houses, deposits, two_house_rule, expected):
    result = it.compute(params=income_params(), rental_income=10_000_000, rental_deposits=deposits,
                        rental_house_count=houses, deemed_rent=DEEMED, two_house_rule=two_house_rule)
    found = [amount for label, amount in result.steps if label.startswith("주택임대 간주임대료")]
    assert found == ([expected] if expected else [])


def test_religious_income_uses_the_expense_table_or_the_wage_rules():
    other = it.compute(params=income_params(), religious_income=30_000_000, religious_bands=RELIGIOUS)
    # 1,600만 + (3천만 - 2천만) x 50% = 2,100만
    assert step(other.steps, "종교인소득 필요경비") == 21_000_000 and step(other.steps, "종교인소득금액") == 9_000_000
    wage = it.compute(params=income_params(), religious_income=30_000_000, religious_as_wage=True)
    assert step(wage.steps, "총급여액") == 30_000_000


@pytest.fixture
def stored_figures(monkeypatch):
    async def penalty(as_of=None):
        return replace(penalty_params(), rates={**penalty_params().rates, "영세율": Decimal("0.005")})

    async def value_added(as_of=None):
        return vat_params()

    async def gift(as_of=None):
        return gift_params()

    monkeypatch.setattr(pt, "load_parameters", penalty)
    monkeypatch.setattr(vat, "load_parameters", value_added)
    monkeypatch.setattr(gt, "load_parameters", gift)


def steps_of(result):
    return [(s.label, s.amount) for s in result.steps]


@pytest.mark.asyncio
async def test_unreported_zero_rated_sales_add_half_a_percent(stored_figures):
    none = await vat.calculate(sales=100_000_000, zero_rated_sales=50_000_000, purchases=20_000_000,
                               penalty_type="무신고", filed_within_months=1)
    # 납부세액 300만, 무신고 20% 60만 + 영세율 5천만 x 0.5% 25만 = 85만, 1개월 내 기한 후 신고 50% 감면
    assert step(steps_of(none), "영세율과세표준 신고불성실가산세") == 250_000
    assert step(steps_of(none), "가산세 합계") == 425_000 and none.final_tax == 3_425_000
    under = await vat.calculate(sales=100_000_000, zero_rated_sales=50_000_000, purchases=20_000_000,
                                penalty_type="과소신고", reported_tax=2_000_000, reported_zero_rated_sales=30_000_000)
    # 덜 낸 100만 x 10% + 덜 신고한 영세율 2천만 x 0.5%
    assert step(steps_of(under), "가산세 합계") == 200_000 and under.final_tax == 1_200_000
    with pytest.raises(CalculationError):
        await vat.calculate(sales=1, reported_zero_rated_sales=1)


@pytest.mark.asyncio
async def test_the_filing_credit_covers_only_the_tax_on_the_reported_base(stored_figures):
    result = await gt.calculate(gift_amount=300_000_000, relation="직계존비속", penalty_type="과소신고",
                                reported_taxable=150_000_000, reported_tax=19_400_000)
    # 과세표준 2.5억 산출세액 4천만, 신고한 1.5억의 산출세액 2천만분만 3% = 60만 → 3,940만 - 신고한 1,940만 = 2천만 x 10%
    assert step(steps_of(result), "신고세액공제(신고한 과세표준 150,000,000원") == 600_000
    assert step(steps_of(result), "가산세 대상 세액") == 20_000_000 and result.final_tax == 22_000_000
    assert not any("처음 신고한 과세표준을 입력하지" in note for note in result.notes)
    with pytest.raises(CalculationError):
        await gt.calculate(gift_amount=300_000_000, relation="직계존비속", reported_taxable=1)


def test_the_decided_retirement_tax_is_the_part_taxed_now():
    half = rt.compute(params=retirement_params(), retirement_pay=100_000_000, service_years=20,
                      pension_transfer=50_000_000, pension_bands=PENSION_BANDS)
    assert (half.calculated_tax, half.decided_tax) == (1_120_000, 560_000)

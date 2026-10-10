"""Comprehensive income tax against the National Tax Service's filing cases and guide examples.

The statutory figures come from the text of 소득세법 제47조, 제59조, 제59조의4 and the 2024~ brackets,
so the formula is checked independently of the database rows.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import financial_income_tax as fit, income_tax as it
from app.services.calculator.errors import CalculationError
from tests.test_calculator import _patch_repository
from tests.test_financial_income_api import current_parameters

DATA = json.loads((Path(__file__).parent / "data" / "nts_income_tax.json").read_text(encoding="utf-8"))


def params():
    band = lambda rows: [{"bracket_from": lower, "rate": Decimal(rate), "progressive_deduction": constant}
                         for lower, rate, constant in rows]
    return it.Parameters(
        financial=current_parameters(), basic_deduction=1_500_000,
        # 제47조: 70% / 350만+40% / 750만+15% / 1,200만+5% / 1,475만+2%, 한도 2천만원
        wage_deduction=band([(0, "0.70", 0), (5_000_000, "0.40", -1_500_000), (15_000_000, "0.15", -5_250_000),
                             (45_000_000, "0.05", -9_750_000), (100_000_000, "0.02", -12_750_000)]),
        wage_deduction_cap=20_000_000,
        # 제59조: 55%, 130만원 초과분 71만5천원 + 30%
        wage_credit=band([(0, "0.55", 0), (1_300_000, "0.30", -325_000)]),
        wage_credit_limits=((0, 740_000, Decimal(0), 740_000), (33_000_000, 740_000, Decimal("0.008"), 660_000),
                            (70_000_000, 660_000, Decimal("0.5"), 500_000),
                            (120_000_000, 500_000, Decimal("0.5"), 200_000)),
        standard_wage=130_000, standard_sincere=120_000, standard_other=70_000)


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


STEP = {"taxable": "과세표준", "wage_deduction": "근로소득공제", "wage_tax": "근로소득에 대한 산출세액",
        "wage_credit": "근로소득세액공제"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_every_published_figure(case):
    result = it.compute(params=params(), **case["inputs"])
    for key, expected in case["expected"].items():
        if key in {"calculated_tax", "decided_tax", "balance"}:
            actual = getattr(result, key)
        elif key == "taxable" and "interest_income" in case["inputs"]:
            actual = result.taxable_income
        else:
            actual = step(result, STEP[key])
        assert actual == expected, (case["id"], key, actual, expected)


def test_wage_deduction_bands_and_cap():
    p = params()
    assert it.wage_deduction(p, 5_000_000) == 3_500_000
    assert it.wage_deduction(p, 15_000_000) == 7_500_000
    assert it.wage_deduction(p, 45_000_000) == 12_000_000
    assert it.wage_deduction(p, 100_000_000) == 14_750_000
    assert it.wage_deduction(p, 400_000_000) == 20_000_000   # 1,475만 + 3억 x 2% = 2,075만 -> 한도


@pytest.mark.parametrize("wage, limit", [(30_000_000, 740_000), (41_000_000, 676_000), (70_000_000, 660_000),
                                         (75_000_000, 500_000), (120_000_000, 500_000), (120_400_000, 300_000),
                                         (200_000_000, 200_000)])
def test_wage_credit_limit_by_total_salary(wage, limit):
    assert it.wage_credit_limit(params(), wage) == limit


@pytest.mark.parametrize("inputs, standard", [
    (dict(wage_income=50_000_000), 130_000),
    (dict(income=60_000_000, expense=20_000_000), 70_000),
    (dict(income=60_000_000, expense=20_000_000, sincere_business=True), 120_000),
    (dict(wage_income=50_000_000, income=30_000_000, sincere_business=True), 130_000),
])
def test_standard_credit_follows_the_kind_of_income(inputs, standard):
    assert step(it.compute(params=params(), **inputs), "표준세액공제") == standard


def test_no_standard_credit_when_special_deductions_are_claimed():
    result = it.compute(params=params(), wage_income=50_000_000, itemized_special_credits=True)
    assert not any(label.startswith("표준세액공제") for label, _ in result.steps)


def test_wage_and_comprehensive_financial_income_share_one_calculation():
    result = it.compute(params=params(), wage_income=60_000_000, interest_income=30_000_000)
    # 근로소득금액 6,000만 - 1,275만 = 4,725만, 과세표준 = 1,000만(기준 초과) + 4,725만 - 150만 = 5,575만
    assert step(result, "근로소득금액") == 47_250_000
    assert step(result, "종합소득 과세표준") == 55_750_000
    general = 55_750_000 * 24 // 100 - 5_760_000 + 2_800_000          # 10,420,000
    assert result.calculated_tax == general
    # 근로소득 산출세액 = 산출세액 x 4,725만 / (4,725만 + 3,000만)
    wage_tax = general * 47_250_000 // 77_250_000
    assert step(result, "근로소득에 대한 산출세액") == wage_tax
    assert step(result, "근로소득세액공제") == 660_000              # 총급여 6,000만 한도: 74만 - 2,700만 x 0.8%
    # 표준세액공제 13만은 원천징수세율 2,000만원분을 뺀 산출세액 안에서 전액 공제된다.
    assert result.decided_tax == general - 660_000 - 130_000
    assert result.prepaid == 4_200_000 and result.balance == result.decided_tax - 4_200_000


def test_financial_income_below_the_threshold_leaves_the_return_unchanged():
    alone = it.compute(params=params(), wage_income=50_000_000)
    with_interest = it.compute(params=params(), wage_income=50_000_000, interest_income=10_000_000)
    assert with_interest.calculated_tax == alone.calculated_tax
    assert with_interest.decided_tax == alone.decided_tax and with_interest.prepaid == 0


def test_business_loss_is_not_carried_to_other_income():
    result = it.compute(params=params(), income=10_000_000, expense=30_000_000, wage_income=40_000_000)
    assert step(result, "사업소득금액") == 0
    assert any("결손금" in note for note in result.notes)


def test_credits_never_make_the_tax_negative():
    result = it.compute(params=params(), wage_income=15_000_000, other_tax_credits=5_000_000)
    assert result.decided_tax == 0


@pytest.mark.asyncio
async def test_calculate_reads_every_statutory_figure_from_the_database():
    with _patch_repository(it), _patch_repository(fit):
        result = await it.calculate(wage_income=41_000_000, personal_deduction_count=4, other_deductions=3_215_000,
                                    itemized_special_credits=True, other_tax_credits=980_500)
    assert (result.tax_type, result.calculated_tax, result.final_tax) == ("종합소득세", 1_797_750, 141_250)


@pytest.mark.asyncio
async def test_missing_credit_limit_table_is_missing_data(monkeypatch):
    from tests import test_calculator as seed
    monkeypatch.setitem(seed._DEDUCTIONS, ("소득세", "근로소득세액공제_한도"), {"amount": None, "condition": {}})
    with _patch_repository(it), _patch_repository(fit), pytest.raises(CalculationError) as error:
        await it.calculate(wage_income=41_000_000)
    assert error.value.code == "missing_tax_data"


@pytest.mark.asyncio
async def test_the_old_financial_calculator_is_an_alias_of_this_one():
    with _patch_repository(it), _patch_repository(fit):
        old = await fit.calculate(interest_income=100_000_000, income_deductions=1_500_000)
        new = await it.calculate(interest_income=100_000_000, personal_deduction_count=1)
    assert old.final_tax == new.final_tax == 15_810_000   # 15,880,000 - 표준세액공제 70,000

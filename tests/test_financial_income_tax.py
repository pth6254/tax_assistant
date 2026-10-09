"""Financial income tax against the National Tax Service's published worked examples.

The 2022 cases are checked with the parameters printed in the same guide (2021~ brackets,
gross-up 11%), so the formula is verified independently of the current-year data.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import financial_income_tax as fit
from app.services.calculator.errors import CalculationError

DATA = json.loads((Path(__file__).parent / "data" / "nts_financial_income_2022.json").read_text(encoding="utf-8"))


def params_2022():
    p = DATA["parameters"]
    lower, brackets = 0, []
    for band in p["brackets"]:
        brackets.append({"bracket_from": lower, "rate": Decimal(band["rate"]),
                         "progressive_deduction": band["progressive_deduction"]})
        lower = band["upper"]
    return fit.Parameters(threshold=p["comprehensive_threshold"], withholding_rate=Decimal(p["withholding_rate"]),
                          non_business_rate=Decimal(p["non_business_loan_rate"]),
                          gross_up_rate=Decimal(p["gross_up_rate"]), brackets=brackets)


def compute(case, **overrides):
    inputs = case["inputs"]
    return fit.compute(params=params_2022(), interest_income=inputs["interest_14"],
                       non_business_interest=inputs["interest_25"], dividend_gross_up=inputs["dividend_gross_up"],
                       dividend_other=inputs["dividend_no_gross_up"], other_income=inputs["other_income"],
                       income_deductions=inputs["deductions"], **overrides)


STEP = {"financial_income": "금융소득 합계", "excess_over_threshold": "기준금액 초과 금융소득",
        "gross_up_base": "배당가산 대상 배당소득(기준금액 초과분)", "gross_up": "배당가산액",
        "general_method_tax": "① 종합과세 방식 산출세액", "separate_method_tax": "② 원천징수세율 방식 산출세액",
        "dividend_tax_credit": "배당세액공제"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_every_published_figure(case):
    withheld = case["id"] != "nts-2022-p173-qa7-3"   # Q&A 7-3: foreign income not withheld at home
    result = compute(case, withheld=withheld)
    steps = dict(result.steps)
    for key, expected in case["expected"].items():
        actual = result.calculated_tax if key == "calculated_tax" else steps[STEP[key]]
        assert actual == expected, (case["id"], key, actual, expected)


def test_worked_example_carries_through_to_the_balance():
    case = DATA["cases"][0]
    result = compute(case)
    # 18,770,000 - 3,300,000 credit; prepaid = (20M bank + 30M dividend) x 14% + 10M loan x 25%
    assert result.decided_tax == 15_470_000
    assert result.prepaid == 9_500_000 and result.balance == 5_970_000
    assert result.method == "general"


def test_case2_takes_the_withholding_method_and_gets_no_credit():
    result = compute(DATA["cases"][2])
    assert result.method == "separate" and dict(result.steps)["배당세액공제"] == 0
    assert result.decided_tax == 15_900_000


def test_threshold_is_filled_by_interest_then_plain_then_gross_up_dividends():
    # 15M interest + 3M plain dividend fill 18M of the 20M; 2M of the 10M gross-up dividend is inside.
    result = fit.compute(params=params_2022(), interest_income=15_000_000, dividend_other=3_000_000,
                         dividend_gross_up=10_000_000)
    steps = dict(result.steps)
    assert steps["배당가산 대상 배당소득(기준금액 초과분)"] == 8_000_000
    assert steps["배당가산액"] == 880_000


def test_withheld_income_at_or_below_the_threshold_ends_with_withholding():
    result = fit.compute(params=params_2022(), interest_income=20_000_000, other_income=30_000_000,
                         income_deductions=5_100_000)
    steps = dict(result.steps)
    assert result.method == "separate_final"
    assert steps["금융소득 원천징수세액(분리과세로 과세 종결)"] == 2_800_000
    # Only the other income is taxed in the return: (30M - 5.1M) x 15% - 1.08M
    assert result.decided_tax == 2_655_000


def test_no_financial_income_belongs_to_the_ordinary_calculator():
    with pytest.raises(CalculationError) as error:
        fit.compute(params=params_2022(), other_income=50_000_000)
    assert error.value.code == "unsupported_condition"

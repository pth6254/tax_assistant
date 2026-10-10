"""Inheritance tax against the National Tax Service's filing cases and guide examples.

The statutory figures come from 상속세 및 증여세법 제18조~제28조·제69조 and 시행령 제9조, which have been the
same for every case year, so the formula is checked without the database.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import inheritance as ih
from app.services.calculator.errors import CalculationError
from tests.test_calculator import _patch_repository

DATA = json.loads((Path(__file__).parent / "data" / "nts_inheritance.json").read_text(encoding="utf-8"))
BRACKETS = [(0, "0.10", 0), (100_000_000, "0.20", 10_000_000), (500_000_000, "0.30", 60_000_000),
            (1_000_000_000, "0.40", 160_000_000), (3_000_000_000, "0.50", 460_000_000)]


def params():
    return ih.Parameters(
        brackets=[{"bracket_from": a, "rate": Decimal(r), "progressive_deduction": d} for a, r, d in BRACKETS],
        amounts={"basic": 200_000_000, "lump_sum": 500_000_000, "spouse_min": 500_000_000,
                 "spouse_max": 3_000_000_000, "child": 50_000_000, "minor_year": 10_000_000,
                 "elderly": 50_000_000, "disabled_year": 10_000_000, "gift_limit_floor": 500_000_000,
                 "funeral_min": 5_000_000, "funeral_max": 10_000_000, "memorial_max": 5_000_000, "minimum": 500_000},
        financial_rate=Decimal("0.2"), financial_min=20_000_000, financial_max=200_000_000,
        surcharge_rate=Decimal("0.3"), surcharge_large_rate=Decimal("0.4"), surcharge_large_threshold=2_000_000_000,
        filing_credit_rate=Decimal("0.03"))


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


STEP = {"base": "상속세 과세가액", "basic": ("기초공제", "일괄공제"), "spouse": "배우자 상속공제",
        "financial": "금융재산 상속공제", "deductions": "상속공제 합계", "taxable": "상속세 과세표준",
        "filing_credit": "신고세액공제"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_every_published_figure(case):
    result = ih.compute(params=params(), **case["inputs"])
    for key, expected in case["expected"].items():
        actual = getattr(result, key) if key in {"calculated_tax", "decided_tax"} else step(result, STEP[key])
        assert actual == expected, (case["id"], key, actual, expected)


def test_spouse_deduction_is_capped_by_the_legal_share_and_thirty_billion():
    # 배우자 혼자 20억 상속, 자녀 2명: 한도 30억 x 1.5/3.5 = 12.86억
    result = ih.compute(params=params(), estate_value=3_000_000_000, has_spouse=True,
                        spouse_inheritance=2_000_000_000, children_count=2)
    assert step(result, "배우자 상속공제") == 1_285_714_285
    huge = ih.compute(params=params(), estate_value=20_000_000_000, has_spouse=True,
                      spouse_inheritance=10_000_000_000, children_count=1)
    assert step(huge, "배우자 상속공제") == 3_000_000_000
    assert any("한도" in note for note in result.notes)


def test_a_sole_spouse_heir_has_no_lump_sum_deduction():
    result = ih.compute(params=params(), estate_value=1_000_000_000, has_spouse=True, spouse_inheritance=1_000_000_000)
    assert step(result, "기초공제와 그 밖의 인적공제") == 200_000_000


@pytest.mark.parametrize("net, deduction", [(15_000_000, 15_000_000), (50_000_000, 20_000_000),
                                           (500_000_000, 100_000_000), (2_000_000_000, 200_000_000)])
def test_financial_deduction_bands(net, deduction):
    assert ih.financial_deduction(params(), net) == deduction


def test_funeral_expenses_have_a_floor_and_a_cap():
    low = ih.compute(params=params(), estate_value=100_000_000)
    high = ih.compute(params=params(), estate_value=100_000_000, funeral_expenses=30_000_000, memorial_expenses=9_000_000)
    assert step(low, "장례비용") == 5_000_000 and step(high, "장례비용") == 15_000_000


def test_prior_gift_tax_is_credited_within_its_share():
    result = ih.compute(params=params(), estate_value=2_005_000_000, children_count=2, prior_gifts=500_000_000,
                        prior_gifts_taxable=450_000_000, prior_gift_tax=80_000_000)
    # 과세표준 20억 -> 산출 6.4억; 한도 6.4억 x 4.5억 / 20억 = 1.44억 -> 증여세 산출세액 8천만 전액 공제
    assert step(result, "상속세 과세표준") == 2_000_000_000
    assert step(result, "증여세액공제") == 80_000_000
    assert result.decided_tax == 640_000_000 - 80_000_000 - (640_000_000 - 80_000_000) * 3 // 100


def test_grandchildren_share_is_surcharged():
    result = ih.compute(params=params(), estate_value=1_505_000_000, children_count=1,
                        skipped_generation_assets=752_500_000)
    # 과세표준 10억 -> 2.4억, 손자녀 몫 절반에 30% -> 3,600만
    assert step(result, "세대생략 할증과세액(30%") == 36_000_000


def test_inconsistent_inputs_are_rejected():
    with pytest.raises(CalculationError) as error:
        ih.compute(params=params(), estate_value=100, financial_assets=200)
    assert error.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_calculate_reads_every_statutory_figure_from_the_database():
    case = next(c for c in DATA["cases"] if c["id"] == "filing-03-taxed")
    with _patch_repository(ih):
        result = await ih.calculate(**case["inputs"])
    assert (result.calculated_tax, result.final_tax) == (44_000_000, 42_680_000)

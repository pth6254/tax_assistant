"""Gift tax against the National Tax Service's filing cases and guide examples.

The statutory figures come from 상속세 및 증여세법 제53조·제53조의2·제55조·제57조·제69조 and the rate
table, which have been the same for every case year, so the formula is checked without the database.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import gift_tax as gt
from app.services.calculator.errors import CalculationError
from tests.test_calculator import _patch_repository

DATA = json.loads((Path(__file__).parent / "data" / "nts_gift_tax.json").read_text(encoding="utf-8"))
BRACKETS = [(0, "0.10", 0), (100_000_000, "0.20", 10_000_000), (500_000_000, "0.30", 60_000_000),
            (1_000_000_000, "0.40", 160_000_000), (3_000_000_000, "0.50", 460_000_000)]


def params(marriage_birth=100_000_000):
    return gt.Parameters(
        brackets=[{"bracket_from": a, "rate": Decimal(r), "progressive_deduction": d} for a, r, d in BRACKETS],
        deductions={"배우자": 600_000_000, "직계존비속": 50_000_000, "기타친족": 10_000_000, "미성년": 20_000_000},
        marriage_birth=marriage_birth, surcharge_rate=Decimal("0.3"), surcharge_large_rate=Decimal("0.4"),
        surcharge_large_threshold=2_000_000_000, filing_credit_rate=Decimal("0.03"), minimum=500_000)


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


STEP = {"base": "증여세 과세가액", "deduction": "증여재산공제(", "taxable": "증여세 과세표준",
        "surcharge": "세대생략 할증", "paid_credit": "기납부세액공제", "filing_credit": "신고세액공제"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_every_published_figure(case):
    result = gt.compute(params=params(), **case["inputs"])
    for key, expected in case["expected"].items():
        actual = getattr(result, key) if key in {"calculated_tax", "decided_tax"} else step(result, STEP[key])
        assert actual == expected, (case["id"], key, actual, expected)


def test_prior_gift_tax_is_credited_not_charged_twice():
    # 1억 + 이전 1억 = 2억 - 5천만 = 1.5억 -> 2천만. 이전 증여만이면 (1억 - 5천만) x 10% = 5백만(추정).
    result = gt.compute(params=params(), gift_amount=100_000_000, relation="직계존비속", prior_gifts_10y=100_000_000)
    assert result.calculated_tax == 20_000_000
    assert step(result, "기납부세액공제") == 5_000_000
    assert result.decided_tax == 14_550_000          # (2천만 - 5백만) x 97%
    assert any("추정치" in note for note in result.notes)


def test_paid_credit_is_capped_by_the_share_of_the_tax_base():
    result = gt.compute(params=params(), gift_amount=200_000_000, relation="직계존비속", prior_gifts_10y=100_000_000,
                        prior_gift_tax=15_000_000, prior_gift_taxable=70_000_000)
    assert step(result, "기납부세액공제") == 11_200_000      # 4천만 x 7천만 / 2.5억


def test_minor_large_generation_skipping_gift_is_surcharged_forty_percent():
    result = gt.compute(params=params(), gift_amount=3_000_000_000, relation="직계존비속", is_minor=True,
                        generation_skipping=True)
    assert step(result, "세대생략 할증과세액(40%)") == result.calculated_tax * 4 // 10


def test_marriage_deduction_is_one_hundred_million_over_a_lifetime():
    result = gt.compute(params=params(), gift_amount=300_000_000, relation="직계존비속", marriage_birth=True,
                        marriage_birth_used=70_000_000)
    assert step(result, "혼인·출산 증여재산공제") == 30_000_000
    with pytest.raises(CalculationError) as error:
        gt.compute(params=params(marriage_birth=None), gift_amount=1, relation="직계존비속", marriage_birth=True)
    assert error.value.code == "unsupported_condition"


def test_below_the_minimum_tax_base_no_tax_is_due():
    result = gt.compute(params=params(), gift_amount=10_400_000, relation="기타친족")
    assert step(result, "증여세 과세표준") == 400_000 and result.decided_tax == 0


def test_late_filing_has_no_filing_credit():
    result = gt.compute(params=params(), gift_amount=500_000_000, relation="직계존비속", filed_on_time=False)
    assert result.decided_tax == 80_000_000


@pytest.mark.parametrize("inputs", [dict(debts=2, gift_amount=1), dict(gift_amount=1, relation="배우자", generation_skipping=True),
                                    dict(gift_amount=1, relation="기타", marriage_birth=True)])
def test_inconsistent_inputs_are_rejected(inputs):
    with pytest.raises(CalculationError) as error:
        gt.compute(params=params(), **inputs)
    assert error.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_calculate_reads_every_statutory_figure_from_the_database():
    with _patch_repository(gt):
        result = await gt.calculate(gift_amount=200_000_000, relation="직계존비속", prior_gifts_10y=100_000_000,
                                    prior_gift_tax=7_000_000, prior_gift_taxable=70_000_000)
    assert (result.calculated_tax, result.final_tax) == (40_000_000, 32_010_000)


@pytest.mark.asyncio
async def test_marriage_deduction_is_missing_before_2024(monkeypatch):
    from tests import test_calculator as seed
    monkeypatch.delitem(seed._DEDUCTIONS, ("증여세", "증여재산공제_혼인출산"))
    with _patch_repository(gt):
        plain = await gt.calculate(gift_amount=100_000_000, relation="직계존비속")
        with pytest.raises(CalculationError) as error:
            await gt.calculate(gift_amount=100_000_000, relation="직계존비속", marriage_birth=True)
    assert plain.final_tax == 4_850_000 and error.value.code == "unsupported_condition"

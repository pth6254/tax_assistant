"""VAT and penalty tax against the National Tax Service's filing cases and guide examples.

The statutory figures come from 부가가치세법 제42조·제46조·제63조·제69조, 시행령 제84조·제111조,
국세기본법 제47조의2~제48조 and 시행령 제27조의4, which are the same for the case years, so the formulas
are checked without the database.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import penalty_tax as pt, vat
from app.services.calculator.errors import CalculationError
from tests.test_calculator import _patch_repository

HERE = Path(__file__).parent / "data"
VAT_CASES = json.loads((HERE / "nts_vat.json").read_text(encoding="utf-8"))["cases"]
PENALTY_CASES = json.loads((HERE / "nts_penalty.json").read_text(encoding="utf-8"))["cases"]
SIMPLE_RATES = {"소매업": "0.15", "음식점업": "0.15", "제조업": "0.20", "농업·임업·어업": "0.20", "숙박업": "0.25",
                "건설업": "0.30", "운수·창고업": "0.30", "정보통신업": "0.30", "부동산임대업": "0.40", "서비스업": "0.40"}


def vat_params(**overrides):
    values = dict(vat_rate=Decimal("0.1"), card_rate=Decimal("0.013"), card_cap=10_000_000, simple_rates=SIMPLE_RATES,
                  simple_input_rate=Decimal("0.005"), exemption_threshold=48_000_000,
                  deemed={"rates": [[200_000_000, "9/109"], [None, "8/108"]],
                          "limits": [[100_000_000, "0.75"], [200_000_000, "0.70"], [None, "0.60"]]},
                  e_filing_credit=10_000)
    values.update(overrides)
    return vat.Parameters(**values)


def penalty_params():
    return pt.Parameters(
        rates={"무신고": Decimal("0.2"), "무신고_부정": Decimal("0.4"), "과소신고": Decimal("0.1"),
               "과소신고_부정": Decimal("0.4"), "수입금액": Decimal("0.0007"), "수입금액_부정": Decimal("0.0014")},
        daily_rate=Decimal("0.00022"),
        amended_bands=[[1, "0.90"], [3, "0.75"], [6, "0.50"], [12, "0.30"], [18, "0.20"], [24, "0.10"]],
        late_return_bands=[[1, "0.50"], [3, "0.30"], [6, "0.20"]])


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


VAT_STEP = {"input_tax": "공제받는 매입세액", "payable": "납부(환급)세액", "deemed": "의제매입세액",
            "card_credit": "신용카드매출전표등 발행세액공제", "common_exempt": "공통매입 중 면세사업분",
            "simple_input": "매입세금계산서등 수취세액공제"}


@pytest.mark.parametrize("case", VAT_CASES, ids=[c["id"] for c in VAT_CASES])
def test_vat_matches_every_published_figure(case):
    result = vat.compute(params=vat_params(), **case["inputs"])
    for key, expected in case["expected"].items():
        actual = getattr(result, key) if key in {"calculated_tax", "decided_tax"} else step(result, VAT_STEP[key])
        assert actual == expected, (case["id"], key, actual, expected)


def test_small_simplified_business_is_exempt_from_payment():
    result = vat.compute(params=vat_params(), sales=40_000_000, is_simplified=True, business_type="음식점업")
    assert result.calculated_tax == 600_000 and result.decided_tax == 0


def test_simplified_credits_cannot_create_a_refund():
    result = vat.compute(params=vat_params(), sales=50_000_000, is_simplified=True, business_type="소매업",
                         purchases=40_000_000, card_sales=50_000_000)
    assert result.decided_tax == 0 and any("환급 없음" in note for note in result.notes)


def test_general_business_can_be_refunded_but_credits_do_not_add_to_it():
    result = vat.compute(params=vat_params(), sales=10_000_000, purchases=30_000_000, card_sales=11_000_000)
    assert result.decided_tax == -2_000_000


def test_card_credit_respects_the_annual_cap_and_eligibility():
    capped = vat.compute(params=vat_params(), sales=1_000_000_000, card_sales=1_100_000_000, card_credit_used=6_000_000)
    assert step(capped, "신용카드매출전표등 발행세액공제") == 4_000_000
    corporate = vat.compute(params=vat_params(), sales=100_000_000, card_sales=110_000_000, card_credit_eligible=False)
    assert corporate.decided_tax == 10_000_000


def test_deemed_input_tax_rate_and_limit_follow_the_tax_base():
    large = vat.compute(params=vat_params(), sales=300_000_000, deemed_purchases=200_000_000)
    # 과세표준 3억 > 2억: 8/108, 한도 3억 x 60% = 1.8억
    assert step(large, "의제매입세액") == 180_000_000 * 8 // 108
    with pytest.raises(CalculationError) as error:
        vat.compute(params=vat_params(deemed=None), sales=100_000_000, deemed_purchases=1)
    assert error.value.code == "unsupported_condition"


@pytest.mark.asyncio
async def test_vat_calculate_reads_every_statutory_figure_from_the_database():
    case = next(c for c in VAT_CASES if c["id"] == "general-restaurant")
    with _patch_repository(vat):
        result = await vat.calculate(**case["inputs"])
    assert result.final_tax == 4_615_571


PENALTY_STEP = {"filing": ("무신고가산세", "과소신고가산세"), "late": "납부지연가산세", "penalty": "가산세 합계",
                "total": "납부할 총액"}


@pytest.mark.parametrize("case", PENALTY_CASES, ids=[c["id"] for c in PENALTY_CASES])
def test_penalty_matches_every_published_figure(case):
    result = pt.compute(params=penalty_params(), **case["inputs"])
    for key, expected in case["expected"].items():
        assert step(result, PENALTY_STEP[key]) == expected, (case["id"], key)


@pytest.mark.parametrize("penalty_type, months, reduced", [
    ("무신고", 1, 1_000_000), ("무신고", 3, 600_000), ("무신고", 6, 400_000), ("무신고", 7, 0),
    ("과소신고", 1, 900_000), ("과소신고", 12, 300_000), ("과소신고", 24, 100_000), ("과소신고", 25, 0),
])
def test_voluntary_late_or_amended_return_reduces_the_filing_penalty(penalty_type, months, reduced):
    base = 2_000_000 if penalty_type == "무신고" else 1_000_000
    result = pt.compute(params=penalty_params(), unpaid_tax=10_000_000, penalty_type=penalty_type,
                        filed_within_months=months)
    assert step(result, "가산세 합계") == base - reduced


def test_late_payment_only():
    result = pt.compute(params=penalty_params(), unpaid_tax=5_000_000, penalty_type="납부지연", days_late=100)
    assert step(result, "가산세 합계") == 110_000


def test_negligent_non_filing_uses_forty_percent_or_the_revenue_floor():
    result = pt.compute(params=penalty_params(), unpaid_tax=1_000_000, is_negligent=True, revenue=1_000_000_000)
    assert step(result, "무신고가산세") == 1_400_000   # max(40만, 10억 x 14/10,000)


@pytest.mark.asyncio
async def test_penalty_calculate_reads_every_statutory_figure_from_the_database():
    with _patch_repository(pt):
        result = await pt.calculate(unpaid_tax=10_000_000, days_late=365)
    assert result.final_tax == 12_803_000

"""
test_calculator.py — 세금 계산기 4종 단위 테스트

DB 의존 없이 실행: repository 함수(get_brackets/get_deduction/get_source_articles)를
db/migrations/001_tax_calculator.sql 시드 데이터와 동일한 값으로 mock 처리.
기대값은 시드 세율표(2024년 기준)로 직접 검산한 값이다.
"""
from contextlib import ExitStack, contextmanager

import pytest
from unittest.mock import AsyncMock, patch

from app.services.calculator import capital_gains, gift_tax, income_tax, inheritance, penalty_tax, vat


# ── 시드 데이터 (001_tax_calculator.sql와 동일) ──────────────────

_BRACKETS: dict[tuple[str, str], list[dict]] = {
    ("소득세", "default"): [
        {"bracket_from": 0,          "bracket_to": 14000000,   "rate": 0.06, "progressive_deduction": 0},
        {"bracket_from": 14000000,   "bracket_to": 50000000,   "rate": 0.15, "progressive_deduction": 1260000},
        {"bracket_from": 50000000,   "bracket_to": 88000000,   "rate": 0.24, "progressive_deduction": 5760000},
        {"bracket_from": 88000000,   "bracket_to": 150000000,  "rate": 0.35, "progressive_deduction": 15440000},
        {"bracket_from": 150000000,  "bracket_to": 300000000,  "rate": 0.38, "progressive_deduction": 19940000},
        {"bracket_from": 300000000,  "bracket_to": 500000000,  "rate": 0.40, "progressive_deduction": 25940000},
        {"bracket_from": 500000000,  "bracket_to": 1000000000, "rate": 0.42, "progressive_deduction": 35940000},
        {"bracket_from": 1000000000, "bracket_to": None,       "rate": 0.45, "progressive_deduction": 65940000},
    ],
    ("상속세", "default"): [
        {"bracket_from": 0,          "bracket_to": 100000000,  "rate": 0.10, "progressive_deduction": 0},
        {"bracket_from": 100000000,  "bracket_to": 500000000,  "rate": 0.20, "progressive_deduction": 10000000},
        {"bracket_from": 500000000,  "bracket_to": 1000000000, "rate": 0.30, "progressive_deduction": 60000000},
        {"bracket_from": 1000000000, "bracket_to": 3000000000, "rate": 0.40, "progressive_deduction": 160000000},
        {"bracket_from": 3000000000, "bracket_to": None,       "rate": 0.50, "progressive_deduction": 460000000},
    ],
}
_BRACKETS[("증여세", "default")]     = _BRACKETS[("상속세", "default")]
_BRACKETS[("양도소득세", "기본")]     = _BRACKETS[("소득세", "default")]
_BRACKETS[("양도소득세", "단기1년미만")] = [{"bracket_from": 0, "bracket_to": None, "rate": 0.70, "progressive_deduction": 0}]
_BRACKETS[("양도소득세", "단기2년미만")] = [{"bracket_from": 0, "bracket_to": None, "rate": 0.60, "progressive_deduction": 0}]
_BRACKETS[("부가가치세", "default")] = [{"bracket_from": 0, "bracket_to": None, "rate": 0.10, "progressive_deduction": 0}]

_DEDUCTIONS: dict[tuple[str, str], dict] = {
    ("소득세", "기본공제"):                     {"amount": 1500000,   "rate": None},
    ("소득세", "표준세액공제_사업자"):           {"amount": 120000,    "rate": None},
    ("소득세", "양도소득기본공제"):              {"amount": 2500000,   "rate": None},
    ("증여세", "증여재산공제_배우자"):           {"amount": 600000000, "rate": None},
    ("증여세", "증여재산공제_직계존비속"):        {"amount": 50000000,  "rate": None},
    ("증여세", "증여재산공제_직계존비속_미성년"): {"amount": 20000000,  "rate": None},
    ("증여세", "증여재산공제_기타친족"):         {"amount": 10000000,  "rate": None},
    ("상속세", "기초공제"):                     {"amount": 200000000, "rate": None},
    ("상속세", "일괄공제"):                     {"amount": 500000000, "rate": None},
    ("상속세", "배우자상속공제_최소"):           {"amount": 500000000, "rate": None},
    ("양도소득세", "장기보유특별공제_3년"):          {"amount": None, "rate": 0.06},
    ("양도소득세", "장기보유특별공제_4년"):          {"amount": None, "rate": 0.08},
    ("양도소득세", "장기보유특별공제_5년"):          {"amount": None, "rate": 0.10},
    ("양도소득세", "장기보유특별공제_10년이상"):     {"amount": None, "rate": 0.20},
    ("양도소득세", "장기보유특별공제_15년이상_1주택"): {"amount": None, "rate": 0.30},
    ("가산세", "무신고가산세_일반"):   {"amount": None, "rate": 0.20},
    ("가산세", "무신고가산세_부정"):   {"amount": None, "rate": 0.40},
    ("가산세", "과소신고가산세_일반"): {"amount": None, "rate": 0.10},
    ("가산세", "과소신고가산세_부정"): {"amount": None, "rate": 0.40},
}


async def _fake_get_brackets(tax_type: str, category: str = "default", as_of=None) -> list[dict]:
    return _BRACKETS.get((tax_type, category), [])


async def _fake_get_deduction(tax_type: str, deduction_name: str, as_of=None) -> dict | None:
    return _DEDUCTIONS.get((tax_type, deduction_name))


@contextmanager
def _patch_repository(module):
    """calculator 모듈 하나의 repository 의존을 시드 데이터 mock으로 교체.

    모듈마다 실제로 import한 repository 함수만 다르므로(예: penalty_tax는
    get_brackets를 쓰지 않음), 모듈에 실제 존재하는 이름만 패치한다.
    """
    prefix = module.__name__
    candidates = {
        "get_brackets":        AsyncMock(side_effect=_fake_get_brackets),
        "get_deduction":       AsyncMock(side_effect=_fake_get_deduction),
        "get_source_articles": AsyncMock(return_value=["테스트 근거조문"]),
    }
    with ExitStack() as stack:
        for name, mock in candidates.items():
            if hasattr(module, name):
                stack.enter_context(patch(f"{prefix}.{name}", mock))
        yield


# ── 소득세 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_income_tax_15pct_bracket():
    """수입 5,000만 → 과세표준 4,850만 → 15% 구간.
    4,850만 × 0.15 - 126만 = 601.5만 → 표준세액공제 12만 차감 = 589.5만."""
    with _patch_repository(income_tax):
        r = await income_tax.calculate(income=50000000)
    assert r.taxable_income == 48500000
    assert r.calculated_tax == 6015000
    assert r.final_tax == 5895000


@pytest.mark.asyncio
async def test_income_tax_38pct_bracket():
    """수입 2억 → 과세표준 1억 9,850만 → 38% 구간.
    1억9,850만 × 0.38 - 1,994만 = 5,549만 → 세액공제 12만 = 5,537만."""
    with _patch_repository(income_tax):
        r = await income_tax.calculate(income=200000000)
    assert r.taxable_income == 198500000
    assert r.calculated_tax == 55490000
    assert r.final_tax == 55370000


@pytest.mark.asyncio
async def test_income_tax_expense_and_multi_deduction():
    """수입 8,000만 - 경비 2,000만, 부양 2명 → 과세표준 5,700만 → 24% 구간.
    5,700만 × 0.24 - 576만 = 792만 → 세액공제 12만 = 780만."""
    with _patch_repository(income_tax):
        r = await income_tax.calculate(income=80000000, expense=20000000, personal_deduction_count=2)
    assert r.taxable_income == 57000000
    assert r.calculated_tax == 7920000
    assert r.final_tax == 7800000


@pytest.mark.asyncio
async def test_income_tax_zero_taxable():
    """수입이 공제보다 작으면 과세표준·세액 모두 0."""
    with _patch_repository(income_tax):
        r = await income_tax.calculate(income=1000000)
    assert r.taxable_income == 0
    assert r.calculated_tax == 0
    assert r.final_tax == 0


# ── 증여세 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gift_tax_spouse():
    """배우자 증여 10억 - 공제 6억 = 과세표준 4억 → 20% 구간.
    4억 × 0.2 - 1,000만 = 7,000만 → 신고세액공제 3%(210만) = 6,790만."""
    with _patch_repository(gift_tax):
        r = await gift_tax.calculate(gift_amount=1000000000, relation="배우자")
    assert r.taxable_income == 400000000
    assert r.calculated_tax == 70000000
    assert r.final_tax == 67900000


@pytest.mark.asyncio
async def test_gift_tax_adult_child():
    """성인 직계비속 1.5억 - 공제 5,000만 = 과세표준 1억 → 10% 구간.
    1억 × 0.1 = 1,000만 → 신고세액공제 3%(30만) = 970만."""
    with _patch_repository(gift_tax):
        r = await gift_tax.calculate(gift_amount=150000000, relation="직계존비속")
    assert r.taxable_income == 100000000
    assert r.calculated_tax == 10000000
    assert r.final_tax == 9700000


@pytest.mark.asyncio
async def test_gift_tax_minor_child_deduction():
    """미성년 직계비속은 공제 2,000만 적용."""
    with _patch_repository(gift_tax):
        r = await gift_tax.calculate(gift_amount=100000000, relation="직계존비속", is_minor=True)
    assert r.taxable_income == 80000000


@pytest.mark.asyncio
async def test_gift_tax_prior_gifts_added():
    """10년 내 기증여는 과세가액에 합산된다."""
    with _patch_repository(gift_tax):
        r = await gift_tax.calculate(gift_amount=100000000, relation="직계존비속", prior_gifts_10y=100000000)
    assert r.taxable_income == 150000000


# ── 상속세 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inheritance_lump_sum_and_spouse():
    """재산 15억, 배우자 5억 상속, 자녀 2명.
    일괄공제 5억(기초 2억+인적 1억보다 큼) + 배우자공제 5억 = 과세표준 5억 → 20% 구간.
    5억 × 0.2 - 1,000만 = 9,000만 → 신고세액공제 3%(270만) = 8,730만."""
    with _patch_repository(inheritance):
        r = await inheritance.calculate(estate_value=1500000000, spouse_inheritance=500000000, children_count=2)
    assert r.taxable_income == 500000000
    assert r.calculated_tax == 90000000
    assert r.final_tax == 87300000


@pytest.mark.asyncio
async def test_inheritance_itemized_exceeds_lump_sum():
    """자녀 7명이면 기초 2억 + 인적 3.5억 = 5.5억 > 일괄공제 5억 → 항목별 공제 적용."""
    with _patch_repository(inheritance):
        r = await inheritance.calculate(estate_value=1000000000, children_count=7)
    assert r.taxable_income == 450000000


@pytest.mark.asyncio
async def test_inheritance_debts_subtracted():
    """채무는 상속재산에서 차감된다."""
    with _patch_repository(inheritance):
        r = await inheritance.calculate(estate_value=800000000, debts=300000000)
    assert r.taxable_income == 0  # 순재산 5억 - 일괄공제 5억


# ── 양도소득세 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capital_gains_long_term_10y():
    """양도 12억 - 취득 7억 - 경비 0.5억 = 차익 4.5억, 10년 보유(20% 공제).
    4.5억 - 0.9억 - 기본공제 250만 = 과세표준 3억 5,750만 → 40% 구간.
    3억5,750만 × 0.4 - 2,594만 = 1억1,706만 + 지방소득세 10% = 1억2,876.6만."""
    with _patch_repository(capital_gains):
        r = await capital_gains.calculate(
            transfer_price=1200000000, acquisition_price=700000000,
            expenses=50000000, holding_years=10,
        )
    assert r.taxable_income == 357500000
    assert r.calculated_tax == 117060000
    assert r.final_tax == 128766000


@pytest.mark.asyncio
async def test_capital_gains_short_term_70pct():
    """1년 미만 보유는 70% 단일세율 (장기보유공제 없음).
    차익 1억 - 기본공제 250만 = 9,750만 × 0.7 = 6,825만 + 지방소득세 682.5만 = 7,507.5만."""
    with _patch_repository(capital_gains):
        r = await capital_gains.calculate(
            transfer_price=500000000, acquisition_price=400000000, holding_years=0,
        )
    assert r.taxable_income == 97500000
    assert r.calculated_tax == 68250000
    assert r.final_tax == 75075000


@pytest.mark.asyncio
async def test_capital_gains_one_home_15y_gets_30pct():
    """15년 보유 1주택자는 30% 장기보유특별공제."""
    with _patch_repository(capital_gains):
        r = await capital_gains.calculate(
            transfer_price=1000000000, acquisition_price=600000000,
            holding_years=15, is_one_home=True,
        )
    # 차익 4억 - 30%(1.2억) - 250만 = 2억 7,750만
    assert r.taxable_income == 277500000


@pytest.mark.asyncio
async def test_capital_gains_no_loss_negative():
    """양도차손이면 세액 0."""
    with _patch_repository(capital_gains):
        r = await capital_gains.calculate(transfer_price=300000000, acquisition_price=400000000)
    assert r.final_tax == 0


# ── 부가가치세 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vat_general_payable():
    """일반과세자: 매출 1억(과세) - 매입 6천만 → 매출세액 1,000만 - 매입세액 600만 = 납부세액 400만."""
    with _patch_repository(vat):
        r = await vat.calculate(sales=100000000, purchases=60000000)
    assert r.taxable_income == 100000000
    assert r.calculated_tax == 10000000
    assert r.final_tax == 4000000


@pytest.mark.asyncio
async def test_vat_refund_when_input_exceeds_output():
    """매입세액이 매출세액보다 크면 환급세액(음수)이 나온다."""
    with _patch_repository(vat):
        r = await vat.calculate(sales=50000000, purchases=80000000)
    assert r.final_tax == -3000000


@pytest.mark.asyncio
async def test_vat_exempt_sales_excluded_from_taxable():
    """영세율·면세 매출은 과세매출에서 제외된다."""
    with _patch_repository(vat):
        r = await vat.calculate(sales=100000000, exempt_sales=30000000)
    assert r.taxable_income == 70000000
    assert r.calculated_tax == 7000000


@pytest.mark.asyncio
async def test_vat_simplified_retail_business():
    """간이과세자 소매업(부가가치율 15%): 매출 5,000만 × 15% × 10% = 75만.
    매입 2,000만 × 0.5% = 10만 공제 → 납부세액 65만."""
    with _patch_repository(vat):
        r = await vat.calculate(
            sales=50000000, purchases=20000000,
            is_simplified=True, business_type="소매업",
        )
    assert r.calculated_tax == 750000
    assert r.final_tax == 650000


# ── 가산세 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_penalty_no_filing_general():
    """일반 무신고: 미납세액 1,000만 × 20% = 200만 가산세, 총 납부액 1,200만."""
    with _patch_repository(penalty_tax):
        r = await penalty_tax.calculate(unpaid_tax=10000000, penalty_type="무신고")
    assert r.calculated_tax == 2000000
    assert r.final_tax == 12000000


@pytest.mark.asyncio
async def test_penalty_no_filing_negligent_40pct():
    """부정행위 무신고는 40% — 1,000만 × 40% = 400만."""
    with _patch_repository(penalty_tax):
        r = await penalty_tax.calculate(unpaid_tax=10000000, penalty_type="무신고", is_negligent=True)
    assert r.calculated_tax == 4000000


@pytest.mark.asyncio
async def test_penalty_underreport_general_10pct():
    """일반 과소신고는 10% — 1,000만 × 10% = 100만."""
    with _patch_repository(penalty_tax):
        r = await penalty_tax.calculate(unpaid_tax=10000000, penalty_type="과소신고")
    assert r.calculated_tax == 1000000


@pytest.mark.asyncio
async def test_penalty_late_payment_daily_rate():
    """납부지연 100일: 1,000만 × 0.022% × 100일 = 22만."""
    with _patch_repository(penalty_tax):
        r = await penalty_tax.calculate(unpaid_tax=10000000, penalty_type="납부지연", days_late=100)
    assert r.calculated_tax == 220000
    assert r.final_tax == 10220000

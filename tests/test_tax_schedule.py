"""
test_tax_schedule.py — 세무 일정 계산 단위 테스트 (규칙 기반, LLM/DB 없음)
"""
from datetime import date

from app.services.tax_schedule_service import compute_upcoming_deadlines


# ── 부가가치세: 사업자 유형별 항목 수 ──────────────────────────────

def test_corporate_has_four_vat_deadlines():
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 1, 1))
    vat_items = [i for i in items if i.tax_type == "부가가치세"]
    assert len(vat_items) == 4


def test_individual_general_has_two_vat_deadlines():
    items = compute_upcoming_deadlines("개인_일반과세", as_of=date(2026, 1, 1))
    vat_items = [i for i in items if i.tax_type == "부가가치세"]
    assert len(vat_items) == 2


def test_simplified_taxpayer_has_one_vat_deadline():
    items = compute_upcoming_deadlines("개인_간이과세", as_of=date(2026, 1, 1))
    vat_items = [i for i in items if i.tax_type == "부가가치세"]
    assert len(vat_items) == 1


def test_unknown_business_type_falls_back_to_individual_general():
    unknown = compute_upcoming_deadlines("알수없음", as_of=date(2026, 1, 1))
    general  = compute_upcoming_deadlines("개인_일반과세", as_of=date(2026, 1, 1))
    assert [(i.tax_type, i.label) for i in unknown] == [(i.tax_type, i.label) for i in general]


# ── 다음 발생일 계산 (연간 반복) ───────────────────────────────────

def test_next_annual_deadline_this_year_if_not_passed():
    """1/1 기준으로 5/31(종합소득세)은 올해 날짜여야 한다."""
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 1, 1))
    income_tax = next(i for i in items if i.tax_type == "종합소득세")
    assert income_tax.due_date == date(2026, 5, 31)


def test_next_annual_deadline_rolls_to_next_year_if_passed():
    """6/1 기준으로 5/31(종합소득세)은 이미 지났으므로 내년 날짜여야 한다."""
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 6, 1))
    income_tax = next(i for i in items if i.tax_type == "종합소득세")
    assert income_tax.due_date == date(2027, 5, 31)


def test_vat_deadline_exact_due_date_counts_as_not_passed():
    """마감일 당일은 아직 지나지 않은 것으로 간주해 같은 날짜를 반환한다."""
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 4, 25))
    q1_provisional = next(i for i in items if i.label == "1기 예정신고·납부")
    assert q1_provisional.due_date == date(2026, 4, 25)
    assert q1_provisional.d_day == 0


# ── 원천세 (매월 10일) ────────────────────────────────────────────

def test_withholding_tax_this_month_if_not_passed():
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 3, 5))
    withholding = next(i for i in items if i.tax_type == "원천세")
    assert withholding.due_date == date(2026, 3, 10)


def test_withholding_tax_rolls_to_next_month_if_passed():
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 3, 15))
    withholding = next(i for i in items if i.tax_type == "원천세")
    assert withholding.due_date == date(2026, 4, 10)


def test_withholding_tax_rolls_to_january_across_year_boundary():
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 12, 15))
    withholding = next(i for i in items if i.tax_type == "원천세")
    assert withholding.due_date == date(2027, 1, 10)


# ── 정렬 및 d_day ─────────────────────────────────────────────────

def test_items_sorted_by_due_date_ascending():
    items = compute_upcoming_deadlines("법인", as_of=date(2026, 1, 1))
    due_dates = [i.due_date for i in items]
    assert due_dates == sorted(due_dates)


def test_d_day_matches_days_until_due_date():
    as_of = date(2026, 1, 1)
    items = compute_upcoming_deadlines("법인", as_of=as_of)
    for item in items:
        assert item.d_day == (item.due_date - as_of).days
        assert item.d_day >= 0

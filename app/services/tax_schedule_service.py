"""
services/tax_schedule_service.py — 세무 일정(신고·납부 기한) 계산

사업자 유형(법인/개인 일반과세/개인 간이과세)에 따른 부가가치세 신고 기한,
종합소득세 확정신고 기한, 매월 원천세 납부 기한을 규칙 기반으로 계산한다.
LLM·DB 조회 없이 순수 계산만 수행한다.

참고: 실제 세법상 예정신고 고지·성실신고확인 대상자 특례 등 세부 예외가 있으나,
이 기능은 참고용 일정 안내이며 법적 효력이 없다 (계산기와 동일한 성격).
"""
from dataclasses import dataclass
from datetime import date

# (월, 일, 라벨) — 사업자 유형별 부가가치세 신고 기한
_VAT_DEADLINES_BY_TYPE: dict[str, list[tuple[int, int, str]]] = {
    "법인": [
        (4, 25, "1기 예정신고·납부"),
        (7, 25, "1기 확정신고·납부"),
        (10, 25, "2기 예정신고·납부"),
        (1, 25, "2기 확정신고·납부"),
    ],
    "개인_일반과세": [
        (7, 25, "1기 확정신고·납부"),
        (1, 25, "2기 확정신고·납부"),
    ],
    "개인_간이과세": [
        (1, 25, "확정신고·납부"),
    ],
}
_DEFAULT_BUSINESS_TYPE = "개인_일반과세"

_INCOME_TAX_DEADLINE = (5, 31, "종합소득세 확정신고·납부")
_WITHHOLDING_TAX_DAY = 10  # 매월 10일


@dataclass
class TaxDeadline:
    tax_type: str
    label: str
    due_date: date
    d_day: int  # 오늘부터 남은 일수 (0 이상만 반환)


def _next_annual_occurrence(month: int, day: int, as_of: date) -> date:
    """매년 반복되는 (월, 일) 중 as_of 이후 가장 가까운 날짜."""
    candidate = date(as_of.year, month, day)
    if candidate < as_of:
        candidate = date(as_of.year + 1, month, day)
    return candidate


def _next_monthly_occurrence(day: int, as_of: date) -> date:
    """매월 반복되는 day일 중 as_of 이후 가장 가까운 날짜."""
    year, month = as_of.year, as_of.month
    candidate = date(year, month, day)
    if candidate < as_of:
        month += 1
        if month > 12:
            month = 1
            year += 1
        candidate = date(year, month, day)
    return candidate


def compute_upcoming_deadlines(
    business_type: str,
    as_of: date | None = None,
) -> list[TaxDeadline]:
    """사업자 유형 기준으로 다가오는 세무 신고·납부 기한 목록을 마감일 순으로 반환한다.

    business_type: '법인' | '개인_일반과세' | '개인_간이과세' (알 수 없는 값은 개인_일반과세로 처리)
    """
    as_of = as_of or date.today()
    vat_rules = _VAT_DEADLINES_BY_TYPE.get(business_type, _VAT_DEADLINES_BY_TYPE[_DEFAULT_BUSINESS_TYPE])

    items: list[TaxDeadline] = []

    for month, day, label in vat_rules:
        due = _next_annual_occurrence(month, day, as_of)
        items.append(TaxDeadline("부가가치세", label, due, (due - as_of).days))

    income_month, income_day, income_label = _INCOME_TAX_DEADLINE
    due = _next_annual_occurrence(income_month, income_day, as_of)
    items.append(TaxDeadline("종합소득세", income_label, due, (due - as_of).days))

    due = _next_monthly_occurrence(_WITHHOLDING_TAX_DAY, as_of)
    items.append(TaxDeadline("원천세", "원천징수이행상황신고·납부", due, (due - as_of).days))

    items.sort(key=lambda d: d.due_date)
    return items

import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


def _apply_progressive_tax(taxable: int, brackets: list[dict]) -> tuple[int, str]:
    """상속세 누진세율 적용 (과세표준 × 세율 - 누진공제). (세액, 적용세율) 반환."""
    for b in sorted(brackets, key=lambda x: x['bracket_from'], reverse=True):
        if taxable > b['bracket_from']:
            tax = int(taxable * float(b['rate'])) - b['progressive_deduction']
            return max(0, tax), f"{int(float(b['rate']) * 100)}%"
    return 0, "0%"

logger = logging.getLogger(__name__)


async def calculate(
    estate_value: int,
    debts: int = 0,
    spouse_inheritance: int = 0,
    children_count: int = 0,
) -> CalculationResult:
    steps: list[TaxStep] = []

    net_estate = max(0, estate_value - debts)
    steps.append(TaxStep(label="순상속재산(재산-채무)", amount=net_estate))

    basic_deduction_row = await get_deduction('상속세', '기초공제')
    basic_deduction = basic_deduction_row['amount'] if basic_deduction_row and basic_deduction_row.get('amount') else 200000000

    personal_deduction = 50000000 * children_count

    lump_sum_row = await get_deduction('상속세', '일괄공제')
    lump_sum = lump_sum_row['amount'] if lump_sum_row and lump_sum_row.get('amount') else 500000000

    itemized_deduction = basic_deduction + personal_deduction
    applied_deduction = max(lump_sum, itemized_deduction)
    steps.append(TaxStep(label="기본공제(일괄공제 or 기초+인적 중 큰 값)", amount=applied_deduction))

    spouse_deduction = 0
    if spouse_inheritance > 0:
        min_spouse_row = await get_deduction('상속세', '배우자상속공제_최소')
        min_spouse = min_spouse_row['amount'] if min_spouse_row and min_spouse_row.get('amount') else 500000000
        spouse_deduction = max(min_spouse, spouse_inheritance)
        steps.append(TaxStep(label="배우자공제", amount=spouse_deduction))

    total_deduction = applied_deduction + spouse_deduction
    taxable = max(0, net_estate - total_deduction)
    steps.append(TaxStep(label="과세표준", amount=taxable))

    brackets = await get_brackets('상속세', 'default')
    if brackets:
        calculated_tax, rate_desc = _apply_progressive_tax(taxable, brackets)
    else:
        calculated_tax, rate_desc = 0, "0%"
        logger.warning("상속세 세율 구간 조회 실패 — 세액 0 처리")

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    filing_credit = int(calculated_tax * 0.03)
    steps.append(TaxStep(label="신고세액공제(3%)", amount=filing_credit))

    final_tax = max(0, calculated_tax - filing_credit)
    steps.append(TaxStep(label="결정세액", amount=final_tax))

    effective_rate = round(final_tax / estate_value, 6) if estate_value > 0 else 0.0
    source_articles = await get_source_articles('상속세')

    return CalculationResult(
        tax_type="상속세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

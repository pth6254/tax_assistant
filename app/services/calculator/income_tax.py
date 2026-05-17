import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


def __apply_progressive_tax(taxable: int, brackets: list[dict]) -> tuple[int, str]:
    """종합소득세 누진세율 적용 (과세표준 × 세율 - 누진공제). (세액, 적용세율) 반환."""
    for b in sorted(brackets, key=lambda x: x['bracket_from'], reverse=True):
        if taxable > b['bracket_from']:
            tax = int(taxable * float(b['rate'])) - b['progressive_deduction']
            return max(0, tax), f"{int(float(b['rate']) * 100)}%"
    return 0, "0%"

logger = logging.getLogger(__name__)


async def calculate(
    income: int,
    expense: int = 0,
    personal_deduction_count: int = 1,
    other_deductions: int = 0,
) -> CalculationResult:
    steps: list[TaxStep] = []

    gross_income = income - expense
    gross_income = max(0, gross_income)
    steps.append(TaxStep(label="소득금액(총수입-필요경비)", amount=gross_income))

    basic_deduction_per_person = 1500000
    deduction_row = await get_deduction('소득세', '기본공제')
    if deduction_row and deduction_row.get('amount'):
        basic_deduction_per_person = deduction_row['amount']

    income_deduction = basic_deduction_per_person * personal_deduction_count + other_deductions
    steps.append(TaxStep(label="소득공제합계", amount=income_deduction))

    taxable = max(0, gross_income - income_deduction)
    steps.append(TaxStep(label="과세표준", amount=taxable))

    brackets = await get_brackets('소득세', 'default')
    if brackets:
        calculated_tax, rate_desc = _apply_progressive_tax(taxable, brackets)
    else:
        calculated_tax, rate_desc = 0, "0%"
        logger.warning("소득세 세율 구간 조회 실패 — 세액 0 처리")

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    tax_credit_row = await get_deduction('소득세', '표준세액공제_사업자')
    tax_credit = tax_credit_row['amount'] if tax_credit_row and tax_credit_row.get('amount') else 120000
    steps.append(TaxStep(label="세액공제(표준세액공제)", amount=tax_credit))

    final_tax = max(0, calculated_tax - tax_credit)
    steps.append(TaxStep(label="결정세액", amount=final_tax))

    effective_rate = round(final_tax / income, 6) if income > 0 else 0.0
    source_articles = await get_source_articles('소득세')

    return CalculationResult(
        tax_type="소득세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

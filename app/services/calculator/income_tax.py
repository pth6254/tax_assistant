from app.services.calculator.errors import CalculationError, require_value
from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.brackets import apply_progressive_tax
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


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

    deduction_row = await get_deduction('소득세', '기본공제')
    basic_deduction_per_person = require_value(deduction_row, 'amount')

    income_deduction = basic_deduction_per_person * personal_deduction_count + other_deductions
    steps.append(TaxStep(label="소득공제합계", amount=income_deduction))

    taxable = max(0, gross_income - income_deduction)
    steps.append(TaxStep(label="과세표준", amount=taxable))

    brackets = await get_brackets('소득세', 'default')
    calculated_tax, rate_desc = apply_progressive_tax(taxable, brackets)

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    tax_credit_row = await get_deduction('소득세', '표준세액공제_사업자')
    tax_credit = require_value(tax_credit_row, 'amount')
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

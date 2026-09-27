from datetime import date
from app.services.calculator.errors import CalculationError, require_value
from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


async def calculate(
    estate_value: int,
    debts: int = 0,
    spouse_inheritance: int = 0,
    children_count: int = 0,
    as_of: date | None = None,
) -> CalculationResult:
    steps: list[TaxStep] = []
    used_rows = []

    net_estate = max(0, estate_value - debts)
    steps.append(TaxStep(label="순상속재산(재산-채무)", amount=net_estate))

    basic_deduction_row = await get_deduction('상속세', '기초공제', as_of=as_of)
    used_rows.append(basic_deduction_row)
    basic_deduction = require_value(basic_deduction_row, 'amount')

    personal_deduction = 50000000 * children_count

    lump_sum_row = await get_deduction('상속세', '일괄공제', as_of=as_of)
    used_rows.append(lump_sum_row)
    lump_sum = require_value(lump_sum_row, 'amount')

    itemized_deduction = basic_deduction + personal_deduction
    applied_deduction = max(lump_sum, itemized_deduction)
    steps.append(TaxStep(label="기본공제(일괄공제 or 기초+인적 중 큰 값)", amount=applied_deduction))

    spouse_deduction = 0
    if spouse_inheritance > 0:
        min_spouse_row = await get_deduction('상속세', '배우자상속공제_최소', as_of=as_of)
        used_rows.append(min_spouse_row)
        min_spouse = require_value(min_spouse_row, 'amount')
        spouse_deduction = max(min_spouse, spouse_inheritance)
        steps.append(TaxStep(label="배우자공제", amount=spouse_deduction))

    total_deduction = applied_deduction + spouse_deduction
    taxable = max(0, net_estate - total_deduction)
    steps.append(TaxStep(label="과세표준", amount=taxable))

    brackets = await get_brackets('상속세', 'default', as_of=as_of)
    used_rows.extend(brackets)
    calculated_tax, rate_desc = apply_progressive_tax(taxable, brackets)

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    filing_credit = int(calculated_tax * 0.03)
    steps.append(TaxStep(label="신고세액공제(3%)", amount=filing_credit))

    final_tax = max(0, calculated_tax - filing_credit)
    steps.append(TaxStep(label="결정세액", amount=final_tax))

    effective_rate = round(final_tax / estate_value, 6) if estate_value > 0 else 0.0
    source_articles = await get_source_articles('상속세', as_of=as_of)

    return CalculationResult(
        tax_type="상속세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(),
                       effective_dates=sorted({str(r['effective_date']) for r in used_rows if r and r.get('effective_date')})),
    )

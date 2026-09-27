from datetime import date
from app.services.calculator.errors import CalculationError, require_value
from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles

_LONG_TERM_DEDUCTION_MAP = [
    (15, True,  '장기보유특별공제_15년이상_1주택'),
    (10, False, '장기보유특별공제_10년이상'),
    (5,  False, '장기보유특별공제_5년'),
    (4,  False, '장기보유특별공제_4년'),
    (3,  False, '장기보유특별공제_3년'),
]


async def calculate(
    transfer_price: int,
    acquisition_price: int,
    expenses: int = 0,
    holding_years: int = 0,
    asset_type: str = '부동산',
    is_one_home: bool = False,
    as_of: date | None = None,
) -> CalculationResult:
    if asset_type != '부동산':
        raise CalculationError('unsupported_condition')
    steps: list[TaxStep] = []

    gain = transfer_price - acquisition_price - expenses
    gain = max(0, gain)
    steps.append(TaxStep(label="양도차익(양도가액-취득가액-경비)", amount=gain))

    long_term_deduction = 0
    used_rows = []
    if asset_type == '부동산' and holding_years >= 3:
        for min_years, need_one_home, deduction_name in _LONG_TERM_DEDUCTION_MAP:
            if holding_years >= min_years and (not need_one_home or is_one_home):
                row = await get_deduction('양도소득세', deduction_name, as_of=as_of)
                used_rows.append(row)
                long_term_deduction = truncate_won(gain, require_value(row, 'rate'))
                steps.append(TaxStep(label=f"장기보유특별공제({deduction_name})", amount=long_term_deduction))
                break

    income_after_ltdc = gain - long_term_deduction
    steps.append(TaxStep(label="양도소득금액", amount=income_after_ltdc))

    basic_deduction_row = await get_deduction('소득세', '양도소득기본공제', as_of=as_of)
    used_rows.append(basic_deduction_row)
    basic_deduction = require_value(basic_deduction_row, 'amount')
    taxable = max(0, income_after_ltdc - basic_deduction)
    steps.append(TaxStep(label="과세표준(기본공제 250만 차감)", amount=taxable))

    if holding_years < 1:
        category = '단기1년미만'
    elif holding_years < 2:
        category = '단기2년미만'
    else:
        category = '기본'

    brackets = await get_brackets('양도소득세', category, as_of=as_of)
    used_rows.extend(brackets)
    calculated_tax, rate_desc = apply_progressive_tax(taxable, brackets)

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    local_tax = truncate_won(calculated_tax, '0.1')
    steps.append(TaxStep(label="지방소득세(10%)", amount=local_tax))

    final_tax = calculated_tax + local_tax
    steps.append(TaxStep(label="합계(산출세액+지방소득세)", amount=final_tax))

    effective_rate = round(final_tax / transfer_price, 6) if transfer_price > 0 else 0.0
    source_articles = await get_source_articles('양도소득세', as_of=as_of)

    return CalculationResult(
        tax_type="양도소득세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(),
                       effective_dates=sorted({str(r['effective_date']) for r in used_rows if r and r.get('effective_date')})),
    )

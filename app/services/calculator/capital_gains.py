import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.brackets import apply_progressive_tax
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


logger = logging.getLogger(__name__)

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
) -> CalculationResult:
    steps: list[TaxStep] = []

    gain = transfer_price - acquisition_price - expenses
    gain = max(0, gain)
    steps.append(TaxStep(label="양도차익(양도가액-취득가액-경비)", amount=gain))

    long_term_deduction = 0
    if asset_type == '부동산' and holding_years >= 3:
        for min_years, need_one_home, deduction_name in _LONG_TERM_DEDUCTION_MAP:
            if holding_years >= min_years and (not need_one_home or is_one_home):
                row = await get_deduction('양도소득세', deduction_name)
                if row and row.get('rate'):
                    long_term_deduction = int(gain * float(row['rate']))
                    steps.append(TaxStep(label=f"장기보유특별공제({deduction_name})", amount=long_term_deduction))
                break

    income_after_ltdc = gain - long_term_deduction
    steps.append(TaxStep(label="양도소득금액", amount=income_after_ltdc))

    basic_deduction_row = await get_deduction('소득세', '양도소득기본공제')
    basic_deduction = basic_deduction_row['amount'] if basic_deduction_row and basic_deduction_row.get('amount') else 2500000
    taxable = max(0, income_after_ltdc - basic_deduction)
    steps.append(TaxStep(label="과세표준(기본공제 250만 차감)", amount=taxable))

    if holding_years < 1:
        category = '단기1년미만'
    elif holding_years < 2:
        category = '단기2년미만'
    else:
        category = '기본'

    brackets = await get_brackets('양도소득세', category)
    if brackets:
        calculated_tax, rate_desc = apply_progressive_tax(taxable, brackets)
    else:
        calculated_tax, rate_desc = 0, "0%"
        logger.warning("양도소득세 세율 구간 조회 실패 category=%s — 세액 0 처리", category)

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    local_tax = int(calculated_tax * 0.1)
    steps.append(TaxStep(label="지방소득세(10%)", amount=local_tax))

    final_tax = calculated_tax + local_tax
    steps.append(TaxStep(label="합계(산출세액+지방소득세)", amount=final_tax))

    effective_rate = round(final_tax / transfer_price, 6) if transfer_price > 0 else 0.0
    source_articles = await get_source_articles('양도소득세')

    return CalculationResult(
        tax_type="양도소득세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

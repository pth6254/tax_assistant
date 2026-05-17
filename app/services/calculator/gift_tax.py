import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.repository import get_brackets, get_deduction, get_source_articles


def __apply_progressive_tax(taxable: int, brackets: list[dict]) -> tuple[int, str]:
    """증여세 누진세율 적용 (과세표준 × 세율 - 누진공제). (세액, 적용세율) 반환."""
    for b in sorted(brackets, key=lambda x: x['bracket_from'], reverse=True):
        if taxable > b['bracket_from']:
            tax = int(taxable * float(b['rate'])) - b['progressive_deduction']
            return max(0, tax), f"{int(float(b['rate']) * 100)}%"
    return 0, "0%"

logger = logging.getLogger(__name__)

_DEDUCTION_NAME_MAP = {
    '배우자':   '증여재산공제_배우자',
    '직계존비속': '증여재산공제_직계존비속',
    '기타친족': '증여재산공제_기타친족',
}
_MINOR_DEDUCTION_NAME = '증여재산공제_직계존비속_미성년'


async def calculate(
    gift_amount: int,
    relation: str = '기타',
    is_minor: bool = False,
    prior_gifts_10y: int = 0,
) -> CalculationResult:
    steps: list[TaxStep] = []

    taxable_base = gift_amount + prior_gifts_10y
    steps.append(TaxStep(label="과세가액(증여액+10년내기증여)", amount=taxable_base))

    deduction = 0
    deduction_name = None
    if relation == '직계존비속' and is_minor:
        deduction_name = _MINOR_DEDUCTION_NAME
    elif relation in _DEDUCTION_NAME_MAP:
        deduction_name = _DEDUCTION_NAME_MAP[relation]

    if deduction_name:
        row = await get_deduction('증여세', deduction_name)
        if row and row.get('amount'):
            deduction = row['amount']

    steps.append(TaxStep(label=f"증여재산공제({relation})", amount=deduction))

    taxable = max(0, taxable_base - deduction)
    steps.append(TaxStep(label="과세표준", amount=taxable))

    brackets = await get_brackets('증여세', 'default')
    if brackets:
        calculated_tax, rate_desc = _apply_progressive_tax(taxable, brackets)
    else:
        calculated_tax, rate_desc = 0, "0%"
        logger.warning("증여세 세율 구간 조회 실패 — 세액 0 처리")

    steps.append(TaxStep(label=f"산출세액({rate_desc})", amount=calculated_tax))

    filing_credit = int(calculated_tax * 0.03)
    steps.append(TaxStep(label="신고세액공제(3%)", amount=filing_credit))

    final_tax = max(0, calculated_tax - filing_credit)
    steps.append(TaxStep(label="결정세액", amount=final_tax))

    effective_rate = round(final_tax / gift_amount, 6) if gift_amount > 0 else 0.0
    source_articles = await get_source_articles('증여세')

    return CalculationResult(
        tax_type="증여세",
        steps=steps,
        taxable_income=taxable,
        calculated_tax=calculated_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

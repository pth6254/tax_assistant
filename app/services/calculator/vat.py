import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.repository import get_brackets, get_source_articles

logger = logging.getLogger(__name__)

# 간이과세자 업종별 부가가치율 (부가가치세법 시행령 제109조 별표) — 실무 빈출 업종만 지원
_SIMPLIFIED_VALUE_ADDED_RATE = {
    "소매업":     0.15,
    "음식점업":   0.15,
    "제조업":     0.20,
    "숙박업":     0.25,
    "건설업":     0.30,
    "서비스업":   0.30,
    "부동산임대업": 0.40,
}
_DEFAULT_SIMPLIFIED_RATE = 0.15


async def calculate(
    sales: int,
    purchases: int = 0,
    exempt_sales: int = 0,
    is_simplified: bool = False,
    business_type: str = "소매업",
) -> CalculationResult:
    steps: list[TaxStep] = []

    taxable_sales = max(0, sales - exempt_sales)
    steps.append(TaxStep(label="과세매출(영세율·면세 제외)", amount=taxable_sales))

    vat_rate = 0.10
    brackets = await get_brackets("부가가치세", "default")
    if brackets:
        vat_rate = float(brackets[0]["rate"])

    if is_simplified:
        value_added_rate = _SIMPLIFIED_VALUE_ADDED_RATE.get(business_type, _DEFAULT_SIMPLIFIED_RATE)
        output_tax = int(taxable_sales * value_added_rate * vat_rate)
        steps.append(TaxStep(
            label=f"납부세액({business_type} 부가가치율{int(value_added_rate * 100)}%×{int(vat_rate * 100)}%)",
            amount=output_tax,
        ))
        input_credit = int(purchases * 0.005)
        steps.append(TaxStep(label="매입세액공제(매입액×0.5%)", amount=input_credit))
        final_tax = max(0, output_tax - input_credit)
    else:
        output_tax = int(taxable_sales * vat_rate)
        steps.append(TaxStep(label=f"매출세액(과세매출×{int(vat_rate * 100)}%)", amount=output_tax))
        input_tax = int(purchases * vat_rate)
        steps.append(TaxStep(label=f"매입세액(매입액×{int(vat_rate * 100)}%)", amount=input_tax))
        final_tax = output_tax - input_tax  # 음수면 환급세액

    steps.append(TaxStep(label="차가감 납부(환급)세액", amount=final_tax))

    effective_rate = round(final_tax / sales, 6) if sales > 0 else 0.0
    source_articles = await get_source_articles("부가가치세") or ["부가가치세법 제37조"]

    return CalculationResult(
        tax_type="부가가치세",
        steps=steps,
        taxable_income=taxable_sales,
        calculated_tax=output_tax,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

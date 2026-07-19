import logging

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.repository import get_deduction, get_source_articles

logger = logging.getLogger(__name__)

# 국세기본법 제47조의2(무신고가산세)·제47조의3(과소신고가산세) 기본 세율.
# 부정행위(사기·기타 부정한 방법)면 두 항목 모두 40%로 상향.
_RATE_DEDUCTION_NAME = {
    ("무신고", False):   "무신고가산세_일반",
    ("무신고", True):    "무신고가산세_부정",
    ("과소신고", False): "과소신고가산세_일반",
    ("과소신고", True):  "과소신고가산세_부정",
}
_FALLBACK_RATE = {
    ("무신고", False):   0.20,
    ("무신고", True):    0.40,
    ("과소신고", False): 0.10,
    ("과소신고", True):  0.40,
}
# 국세기본법 제47조의4·시행령 제27조의4(납부지연가산세) — 1일 10만분의 22(0.022%, 연 약 8.03%).
# tax_deductions.rate 컬럼(NUMERIC(5,4))은 소수점 4자리까지만 저장 가능해 이 정밀도를
# 담을 수 없으므로 DB 시드 대신 코드 상수로 고정한다.
_DAILY_LATE_RATE = 0.00022


async def calculate(
    unpaid_tax: int,
    penalty_type: str = "무신고",
    is_negligent: bool = False,
    days_late: int = 0,
) -> CalculationResult:
    steps: list[TaxStep] = []
    steps.append(TaxStep(label="본세(무신고·과소신고·미납 세액)", amount=unpaid_tax))

    if penalty_type == "납부지연":
        penalty = int(unpaid_tax * _DAILY_LATE_RATE * days_late)
        steps.append(TaxStep(
            label=f"납부지연가산세(1일 {_DAILY_LATE_RATE * 100:.4f}%×{days_late}일)",
            amount=penalty,
        ))
    else:
        deduction_name = _RATE_DEDUCTION_NAME.get((penalty_type, is_negligent))
        row = await get_deduction("가산세", deduction_name) if deduction_name else None
        rate = float(row["rate"]) if row and row.get("rate") is not None else _FALLBACK_RATE.get((penalty_type, is_negligent), 0.20)
        penalty = int(unpaid_tax * rate)
        label = f"{penalty_type}가산세({int(rate * 100)}%{' · 부정행위' if is_negligent else ''})"
        steps.append(TaxStep(label=label, amount=penalty))

    final_tax = unpaid_tax + penalty
    steps.append(TaxStep(label="납부할 총액(본세+가산세)", amount=final_tax))

    effective_rate = round(penalty / unpaid_tax, 6) if unpaid_tax > 0 else 0.0
    source_articles = await get_source_articles("가산세") or [
        "국세기본법 제47조의2", "국세기본법 제47조의3", "국세기본법 제47조의4",
    ]

    return CalculationResult(
        tax_type="가산세",
        steps=steps,
        taxable_income=unpaid_tax,
        calculated_tax=penalty,
        final_tax=final_tax,
        effective_rate=effective_rate,
        source_articles=source_articles,
    )

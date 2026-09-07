"""DB 세율표 기반 계산 실행. LLM 선택은 services/tools에서 담당한다."""
from dataclasses import dataclass

from app.schemas.calculator import (
    CalculationResult,
    CapitalGainsRequest,
    GiftTaxRequest,
    IncomeTaxRequest,
    InheritanceRequest,
    PenaltyTaxRequest,
    VatRequest,
)
from app.services.calculator import capital_gains, gift_tax, income_tax, inheritance, penalty_tax, vat

CALCULATORS = {
    "income_tax":    (IncomeTaxRequest,    income_tax),
    "capital_gains": (CapitalGainsRequest, capital_gains),
    "inheritance":   (InheritanceRequest,  inheritance),
    "gift":          (GiftTaxRequest,      gift_tax),
    "vat":           (VatRequest,          vat),
    "penalty_tax":   (PenaltyTaxRequest,   penalty_tax),
}

@dataclass
class CalcRun:
    """계산기 실행 결과 — LLM 컨텍스트 + 프론트엔드 왕복 연결(계산기 화면 프리필)용 메타데이터."""
    context: str
    tool: str
    params: dict


def format_calculation_context(result: CalculationResult) -> str:
    """계산 결과를 LLM 컨텍스트 문자열로 포맷한다."""
    lines = [f"세목: {result.tax_type}"]
    lines += [f"- {s.label}: {s.amount:,}원" for s in result.steps]
    lines.append(f"- 실효세율: {result.effective_rate * 100:.2f}%")
    if result.source_articles:
        lines.append("근거 조문: " + ", ".join(result.source_articles))
    return "\n".join(lines)


async def run_calculation(tool: str, params: dict) -> CalcRun:
    """검증된 입력으로 계산한다. 실패는 호출 계층에서 처리한다."""
    schema, calculator_module = CALCULATORS[tool]
    req = schema.model_validate(params, strict=True, extra="forbid")
    resolved_params = req.model_dump()
    result = await calculator_module.calculate(**resolved_params)
    return CalcRun(
        context=format_calculation_context(result),
        tool=tool,
        params=resolved_params,
    )

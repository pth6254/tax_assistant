"""DB 세율표 기반 계산 실행. LLM 선택은 services/tools에서 담당한다."""
from dataclasses import dataclass

from app.schemas.calculator import (
    CalculationResult,
    CapitalGainsRequest,
    FinancialIncomeTaxRequest,
    GiftTaxRequest,
    IncomeTaxRequest,
    InheritanceRequest,
    PenaltyTaxRequest,
    RetirementTaxRequest,
    VatRequest,
)
from app.services.calculator import (capital_gains, financial_income_tax, gift_tax, income_tax, inheritance,
                                     penalty_tax, retirement, vat)

CALCULATORS = {
    "income_tax":    (IncomeTaxRequest,    income_tax),
    "financial_income_tax": (FinancialIncomeTaxRequest, financial_income_tax),
    "capital_gains": (CapitalGainsRequest, capital_gains),
    "inheritance":   (InheritanceRequest,  inheritance),
    "gift":          (GiftTaxRequest,      gift_tax),
    "vat":           (VatRequest,          vat),
    "penalty_tax":   (PenaltyTaxRequest,   penalty_tax),
    "retirement":    (RetirementTaxRequest, retirement),
}

@dataclass
class CalcRun:
    """계산기 실행 결과 — LLM 컨텍스트 + 프론트엔드 왕복 연결(계산기 화면 프리필)용 메타데이터."""
    context: str
    tool: str
    params: dict
    verification: dict | None = None
    result: CalculationResult | None = None   # 채팅 답변의 표를 그리는 원본
    assumptions: tuple = ()                    # 채팅 질문을 읽으며 둔 가정


def format_calculation_context(result: CalculationResult) -> str:
    """계산 결과를 LLM 컨텍스트 문자열로 포맷한다."""
    lines = [f"세목: {result.tax_type}"]
    if result.basis:
        lines.append(f"적용 세법 기준일: {result.basis.queried_on}")
    lines += [f"- {s.label}: {s.amount:,}원" for s in result.steps]
    lines.append(f"- 실효세율: {result.effective_rate * 100:.2f}%")
    if result.source_articles:
        lines.append("근거 조문: " + ", ".join(result.source_articles))
    lines += [f"- 참고: {note}" for note in result.notes]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def format_calculation_answer(run: CalcRun) -> str:
    """채팅 답변: 결론 한 줄, 계산 단계 표, 가정·참고·근거. 표는 화면이 마크다운(GFM)으로 그린다."""
    result = run.result
    if result is None:
        return run.context
    final = result.final_tax
    headline = (f"말씀하신 조건에서 **{result.tax_type} 환급받을 세액은 {-final:,}원**으로 계산됩니다." if final < 0 else
                f"말씀하신 조건에서 **{result.tax_type} 납부할 세액은 {final:,}원**으로 계산됩니다.")
    lines = [headline, "", "**계산 과정**", "", "| 항목 | 금액 |", "| --- | ---: |"]
    lines += [f"| {_cell(step.label)} | {step.amount:,}원 |" for step in result.steps]
    lines.append(f"| 실효세율 | {result.effective_rate * 100:.2f}% |")
    if run.assumptions:
        lines += ["", "**계산에 쓴 가정**", "", *[f"- {item}" for item in run.assumptions]]
    if result.notes:
        lines += ["", "**참고**", "", *[f"- {note}" for note in result.notes]]
    basis = [f"적용 세법 기준일: {result.basis.queried_on}"] if result.basis else []
    if result.source_articles:
        basis.append("근거 조문: " + ", ".join(result.source_articles))
    if basis:
        lines += ["", *[f"- {item}" for item in basis]]
    return "\n".join(lines)


async def run_calculation(tool: str, params: dict) -> CalcRun:
    """검증된 입력으로 계산한다. 실패는 호출 계층에서 처리한다."""
    schema, calculator_module = CALCULATORS[tool]
    req = schema.model_validate(params, strict=True, extra="forbid")
    result = await calculator_module.calculate(**req.model_dump())
    # The prefill params travel as JSON (a date as its ISO string).
    return CalcRun(
        context=format_calculation_context(result),
        tool=tool,
        params=req.model_dump(mode="json"),
        result=result,
    )

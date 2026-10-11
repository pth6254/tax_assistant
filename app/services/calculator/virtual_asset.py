"""가상자산 소득세 참고 계산(기타소득 분리과세).

소득세법 제21조 제1항 제27호(가상자산 양도·대여 소득은 기타소득), 제37조 제5항(2027년 1월 1일 전부터 보유한
가상자산의 취득가액은 2026년 12월 31일 당시 시가와 실제 취득가액 중 큰 금액), 제64조의3 제2항(가상자산소득금액에서
250만원을 뺀 금액의 20%)을 따른다. 과세는 2027년 1월 1일 이후 양도분부터이므로(2027-01-01 시행본), 그 전 기준일에는
과세되지 않음과 2027년 이후 양도했을 때의 세액을 함께 보인다. 법정 수치는 DB에서 읽는다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import truncate_won
from app.services.calculator.errors import CalculationError
from app.services.calculator.repository import get_deduction

RATE_ROW, START = "가상자산소득", date(2027, 1, 1)

SCOPE_NOTES = (
    "거주자별 총평균법으로 계산한 같은 해 전체 가상자산 손익을 한 번에 입력해야 합니다(종목별 손익 통산). 비거주자, "
    "가상자산 대여소득, 취득가액 확인이 곤란한 경우의 의제필요경비는 계산하지 않았습니다.",
)


@dataclass(frozen=True)
class Parameters:
    rate: Decimal
    basic_deduction: int
    local_ratio: Decimal
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    notes: list


def compute(*, params, transfer_price, acquisition_price, expenses=0, held_before_2027=False, value_2026_end=0,
            taxed=True):
    if value_2026_end and not held_before_2027:
        raise CalculationError("invalid_input")
    acquisition = max(acquisition_price, value_2026_end) if held_before_2027 else acquisition_price
    steps = [("양도가액", transfer_price)]
    if held_before_2027:
        steps.append(("취득가액(실제 취득가액과 2026-12-31 시가 중 큰 금액)", acquisition))
    else:
        steps.append(("취득가액", acquisition))
    if expenses:
        steps.append(("필요경비(거래수수료 등)", expenses))
    income = max(0, transfer_price - acquisition - expenses)
    taxable = max(0, income - params.basic_deduction)
    tax = truncate_won(taxable, params.rate)
    local = truncate_won(tax, params.local_ratio)
    steps += [("가상자산소득금액", income), ("기본공제", min(income, params.basic_deduction)), ("과세표준", taxable)]
    notes = []
    if taxed:
        steps += [(f"산출세액({params.rate * 100:.0f}%, 분리과세)", tax), ("지방소득세(별도, 소득세의 10%)", local)]
        notes.append("가상자산소득은 다른 종합소득과 합산하지 않고 분리과세하며, 다음 해 5월에 신고·납부합니다.")
        return Computation(steps, taxable, tax, tax, notes)
    steps += [("이번 양도의 세금(2027년 전 양도는 과세 대상 아님)", 0),
              (f"같은 조건으로 2027년 이후 양도하면 낼 세액({params.rate * 100:.0f}%)", tax)]
    notes.append("가상자산 양도소득은 2027년 1월 1일 이후 양도분부터 과세됩니다. 그 전에 판 것은 소득세가 없습니다.")
    return Computation(steps, taxable, 0, 0, notes)


async def load_parameters(as_of: date | None = None) -> tuple[Parameters, bool]:
    """(수치, 기준일에 과세되는지). 시행 전 기준일이면 시행일 수치를 읽어 2027년 이후 세액을 보인다."""
    as_of = as_of or date.today()
    taxed = as_of >= START
    row = await get_deduction("소득세", RATE_ROW, as_of=as_of if taxed else START)
    condition = (row or {}).get("condition") or {}
    if row is None or row.get("rate") is None or "local_ratio" not in condition:
        raise CalculationError("missing_tax_data")
    params = Parameters(rate=Decimal(str(row["rate"])), basic_deduction=int(row["amount"]),
                        local_ratio=Decimal(condition["local_ratio"]),
                        effective_dates=(str(row["effective_date"]),), sources=(row["source_article"],))
    return params, taxed


async def calculate(transfer_price: int, acquisition_price: int, expenses: int = 0, held_before_2027: bool = False,
                    value_2026_end: int = 0, as_of: date | None = None) -> CalculationResult:
    params, taxed = await load_parameters(as_of)
    result = compute(params=params, transfer_price=transfer_price, acquisition_price=acquisition_price,
                     expenses=expenses, held_before_2027=held_before_2027, value_2026_end=value_2026_end, taxed=taxed)
    return CalculationResult(
        tax_type="가상자산 소득세(기타소득 분리과세)",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / transfer_price, 6) if transfer_price else 0.0,
        source_articles=["소득세법 제21조", "소득세법 제37조", *params.sources],
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

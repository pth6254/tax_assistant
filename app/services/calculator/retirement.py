"""퇴직소득세 참고 계산(2020년 이후 퇴직): 퇴직소득금액 → 근속연수공제 → 환산급여 → 환산급여공제 → 과세표준
→ 환산산출세액(기본세율) → 산출세액(÷12 x 근속연수).

소득세법 제22조(퇴직소득), 제48조(퇴직소득공제: 근속연수공제·환산급여공제), 제55조 제2항(퇴직소득 산출세액)을
따른다. 근속연수는 1년 미만의 기간을 1년으로 본다. 산식은 국세청 「퇴직소득」 안내의 계산 사례로 검증한다
(tests/data/nts_retirement.json). 법정 수치(근속연수공제표, 환산급여공제표, 기본세율)는 DB에서 읽는다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator import penalty_tax
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError
from app.services.calculator.repository import get_brackets, get_deduction

SERVICE_DEDUCTION, LOCAL_RATIO = "퇴직소득_근속연수공제", "퇴직소득_지방소득세_비율"

SCOPE_NOTES = (
    "2016~2019년 퇴직분의 종전·개정 규정 안분, 임원 퇴직금 한도 초과분(근로소득), 비과세 퇴직급여, 외국납부세액공제, "
    "퇴직소득을 연금계좌로 옮겨 연금으로 받는 경우(과세이연)는 계산하지 않았습니다.",
    "근속연수는 중간정산·여러 회사 합산 시 중복 기간을 뺀 정산근속연수를 입력해야 합니다.",
)


@dataclass(frozen=True)
class Parameters:
    service_tiers: list      # [[근속연수 상한(None=초과), 기준액, 연당 금액, 기준 연수], ...]
    converted_bands: list    # 환산급여공제: rate x 환산급여 - progressive_deduction(음수: 더하는 금액)
    brackets: list
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


def service_deduction(params, years):
    """제48조 제1항 제1호: 근속연수공제."""
    for upper, base, per_year, start in params.service_tiers:
        if upper is None or years <= upper:
            return base + per_year * (years - start)
    raise CalculationError("missing_tax_data")


def compute(*, params, retirement_pay, service_years, prepaid_tax=0):
    if service_years <= 0:
        raise CalculationError("invalid_input")
    deduction = min(service_deduction(params, service_years), retirement_pay)
    converted = int(Decimal(retirement_pay - deduction) * 12 / service_years)
    converted_deduction = min(apply_progressive_tax(converted, params.converted_bands)[0], converted)
    taxable = converted - converted_deduction
    converted_tax, rate = apply_progressive_tax(taxable, params.brackets)
    calculated = int(Decimal(converted_tax) * service_years / 12)
    local = truncate_won(calculated, params.local_ratio)
    steps = [("퇴직소득금액(퇴직급여)", retirement_pay),
             (f"근속연수공제(근속 {service_years}년)", deduction),
             ("환산급여((퇴직소득금액-근속연수공제) x 12 / 근속연수)", converted),
             ("환산급여공제", converted_deduction),
             ("퇴직소득 과세표준", taxable),
             (f"환산산출세액(기본세율 {rate})", converted_tax),
             ("퇴직소득 산출세액(환산산출세액 / 12 x 근속연수)", calculated)]
    if prepaid_tax:
        steps.append(("기납부(원천징수)세액", prepaid_tax))
    balance = calculated - prepaid_tax
    steps += [("차감 납부할 세액" if balance >= 0 else "환급받을 세액", abs(balance)),
              ("지방소득세(별도, 산출세액의 10%)", local)]
    notes = ["퇴직소득은 다른 소득과 합산하지 않고 따로 과세합니다(분류과세). 결정세액은 퇴직소득세(국세)이고 "
             "지방소득세는 별도로 표시했습니다."]
    return Computation(steps, taxable, calculated, calculated, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    service = await get_deduction("소득세", SERVICE_DEDUCTION, as_of=as_of)
    local = await get_deduction("소득세", LOCAL_RATIO, as_of=as_of)
    bands = await get_brackets("소득세", "퇴직_환산급여공제", as_of=as_of)
    brackets = await get_brackets("소득세", "default", as_of=as_of)
    tiers = ((service or {}).get("condition") or {}).get("tiers")
    if not tiers or not local or local.get("rate") is None:
        raise CalculationError("missing_tax_data")
    used = [r for r in [service, local, *bands, *brackets] if r]
    return Parameters(
        service_tiers=tiers, converted_bands=bands, brackets=brackets, local_ratio=Decimal(str(local["rate"])),
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r.get("source_article")})))


async def calculate(retirement_pay: int, service_years: int, prepaid_tax: int = 0,
                    as_of: date | None = None, **penalty) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(params=params, retirement_pay=retirement_pay, service_years=service_years, prepaid_tax=prepaid_tax)
    summary = CalculationResult(
        tax_type="퇴직소득세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / retirement_pay, 6) if retirement_pay else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])
    return await penalty_tax.attach(summary, max(0, result.decided_tax - prepaid_tax), as_of=as_of, **penalty)

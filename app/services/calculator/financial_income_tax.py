"""금융소득 종합과세를 포함한 종합소득세 참고 계산.

소득세법 제14조(이자소득등의 종합과세기준금액), 제17조 제3항(배당가산), 제56조(배당세액공제),
제62조(이자소득 등에 대한 종합과세 시 세액 계산의 특례), 제129조(원천징수세율)를 따른다.
산식은 국세청 「2022년 귀속 금융소득종합과세 해설」의 계산 사례로 검증한다
(tests/data/nts_financial_income_2022.json). 법정 수치는 DB(tax_deductions, tax_brackets)에서
읽으며 코드에 상수로 두지 않는다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일의 수치를
읽어 호출한다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

THRESHOLD = "이자소득등종합과세기준금액"
WITHHOLDING_RATE = "금융소득원천징수율"
NON_BUSINESS_RATE = "비영업대금이익원천징수율"
GROSS_UP_RATE = "배당가산율"

SCOPE_NOTES = (
    "출자공동사업자 배당(원천징수 25%), 비거주자, 국외 금융소득의 외국납부세액공제, 분리과세·비과세 금융상품, "
    "결손금 공제, 배당세액공제 외의 세액공제와 지방소득세는 계산하지 않았습니다.",
    "금액은 연간 총수입금액 기준의 참고 계산이며 실제 신고세액을 확정하지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    threshold: int
    withholding_rate: Decimal
    non_business_rate: Decimal
    gross_up_rate: Decimal
    brackets: list
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    prepaid: int
    balance: int
    method: str
    notes: list


def _progressive(amount, brackets):
    return apply_progressive_tax(max(0, amount), brackets)[0]


def compute(*, params, interest_income=0, non_business_interest=0, dividend_gross_up=0,
            dividend_other=0, other_income=0, income_deductions=0, withheld=True):
    interest, loans, gross_up_dividend, plain_dividend = (
        interest_income, non_business_interest, dividend_gross_up, dividend_other)
    financial = interest + loans + gross_up_dividend + plain_dividend
    if financial <= 0:
        # Without financial income the ordinary income tax calculator applies.
        raise CalculationError("unsupported_condition")
    r14, r25 = params.withholding_rate, params.non_business_rate
    statutory_withholding = truncate_won(financial - loans, r14) + truncate_won(loans, r25)
    prepaid = statutory_withholding if withheld else 0
    other_base = max(0, other_income - income_deductions)
    # ② 금융소득을 원천징수세율로 과세하는 방식(제62조 제2호)
    separate = _progressive(other_base, params.brackets) + truncate_won(loans, r25) + truncate_won(financial - loans, r14)
    steps = [("금융소득 합계", financial)]
    notes = []

    if financial <= params.threshold:
        if withheld:
            other_tax = _progressive(other_base, params.brackets)
            steps += [("금융소득 원천징수세액(분리과세로 과세 종결)", statutory_withholding),
                      ("다른 종합소득 과세표준", other_base), ("다른 종합소득 산출세액", other_tax)]
            notes.append("금융소득이 종합과세기준금액 이하이고 국내에서 원천징수되어 분리과세로 과세가 끝납니다. "
                         "원천징수세액은 법정 원천징수세율로 추정한 금액입니다.")
            return Computation(steps, other_base, other_tax, other_tax, 0, other_tax, "separate_final", notes)
        # Not withheld at home: it joins the return but is taxed at withholding rates.
        steps += [("다른 종합소득 과세표준", other_base),
                  ("종합소득 산출세액(원천징수세율 적용 방식)", separate),
                  ("결정세액", separate), ("기납부세액(국내 원천징수 없음)", 0), ("차감 납부할 세액", separate)]
        notes.append("국내에서 원천징수되지 않은 금융소득은 기준금액 이하여도 종합소득 신고에 포함하고 원천징수세율로 계산합니다.")
        return Computation(steps, other_base, separate, separate, 0, separate, "separate", notes)

    # The threshold is filled by interest, then dividends without gross-up, then those with it
    # (소득세법 시행령 제116조의2); only gross-up dividends above it are grossed up.
    remaining = params.threshold
    for amount in (interest + loans, plain_dividend):
        remaining -= min(amount, remaining)
    gross_up_base = gross_up_dividend - min(gross_up_dividend, remaining)
    gross_up = truncate_won(gross_up_base, params.gross_up_rate)
    excess = financial - params.threshold
    taxable = max(0, excess + gross_up + other_income - income_deductions)
    # ① 기준금액 초과분은 기본세율, 기준금액은 원천징수세율(제62조 제1호)
    general = _progressive(taxable, params.brackets) + truncate_won(params.threshold, r14)
    calculated = max(general, separate)
    credit = max(0, min(gross_up, calculated - separate))   # 제56조
    decided = calculated - credit
    balance = decided - prepaid
    method = "general" if general >= separate else "separate"
    steps += [("종합과세기준금액", params.threshold), ("기준금액 초과 금융소득", excess),
              ("배당가산 대상 배당소득(기준금액 초과분)", gross_up_base), ("배당가산액", gross_up),
              ("종합소득 과세표준(종합과세 방식)", taxable),
              ("① 종합과세 방식 산출세액", general), ("② 원천징수세율 방식 산출세액", separate),
              ("종합소득 산출세액(①·② 중 큰 금액)", calculated), ("배당세액공제", credit), ("결정세액", decided),
              ("기납부세액(법정 원천징수세율로 추정)" if withheld else "기납부세액(국내 원천징수 없음)", prepaid),
              ("차감 납부할 세액" if balance >= 0 else "환급받을 세액", abs(balance))]
    notes.append("산출세액은 ① 종합과세 방식과 ② 원천징수세율 방식 중 큰 금액입니다(비교과세): "
                 + ("①이 더 큽니다." if method == "general" else "②가 더 큽니다."))
    if withheld:
        notes.append("기납부세액은 법정 원천징수세율로 추정한 금액이며 실제 원천징수영수증 금액과 다를 수 있습니다.")
    return Computation(steps, taxable, calculated, decided, prepaid, balance, method, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    rows = {name: await get_deduction("소득세", name, as_of=as_of)
            for name in (THRESHOLD, WITHHOLDING_RATE, NON_BUSINESS_RATE, GROSS_UP_RATE)}
    brackets = await get_brackets("소득세", "default", as_of=as_of)
    return Parameters(
        threshold=int(require_value(rows[THRESHOLD], "amount")),
        withholding_rate=Decimal(str(require_value(rows[WITHHOLDING_RATE], "rate"))),
        non_business_rate=Decimal(str(require_value(rows[NON_BUSINESS_RATE], "rate"))),
        gross_up_rate=Decimal(str(require_value(rows[GROSS_UP_RATE], "rate"))),
        brackets=brackets,
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in [*rows.values(), *brackets]
                                      if r and r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in [*rows.values(), *brackets]
                              if r and r.get("source_article")})))


async def calculate(interest_income: int = 0, non_business_interest: int = 0, dividend_gross_up: int = 0,
                    dividend_other: int = 0, other_income: int = 0, income_deductions: int = 0,
                    withheld: bool = True, as_of: date | None = None) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(params=params, interest_income=interest_income, non_business_interest=non_business_interest,
                     dividend_gross_up=dividend_gross_up, dividend_other=dividend_other,
                     other_income=other_income, income_deductions=income_deductions, withheld=withheld)
    total_income = interest_income + non_business_interest + dividend_gross_up + dividend_other + other_income
    return CalculationResult(
        tax_type="소득세(금융소득 종합과세)",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / total_income, 6) if total_income else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

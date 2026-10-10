"""종합소득세 참고 계산: 소득 종류별 소득금액 → 금융소득 비교과세 → 종합소득공제 → 소득 종류별 세액공제 → 기납부세액.

소득세법 제47조(근로소득공제), 제55조(세율), 제59조(근로소득세액공제), 제59조의4 제9항(표준세액공제),
제61조(세액공제액의 한도), 제62조(금융소득 비교과세)와 시행령 제119조의3(근로소득·원천징수세율 적용
금융소득에 대한 산출세액)을 따른다. 금융소득 부분은 `financial_income_tax.compare`가 계산한다.
산식은 국세청 종합소득세 신고서 작성사례와 「2026 세금절약가이드 Ⅰ」의 계산 사례로 검증한다
(tests/data/nts_income_tax.json). 법정 수치는 DB(tax_deductions, tax_brackets)에서 읽는다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일의 수치를 읽어 호출한다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator import financial_income_tax
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

BASIC = "기본공제"
WAGE_DEDUCTION_CAP = "근로소득공제_한도"
WAGE_CREDIT_LIMIT = "근로소득세액공제_한도"
STANDARD_WAGE, STANDARD_SINCERE, STANDARD_OTHER = "표준세액공제_근로", "표준세액공제_성실사업자", "표준세액공제_그밖"
DEDUCTION_NAMES = (BASIC, WAGE_DEDUCTION_CAP, WAGE_CREDIT_LIMIT, STANDARD_WAGE, STANDARD_SINCERE, STANDARD_OTHER)

SCOPE_NOTES = (
    "결손금·이월결손금, 기장세액공제, 세액감면, 가산세, 분리과세를 선택한 소득, 출자공동사업자 배당, "
    "비거주자, 국외소득의 외국납부세액공제와 지방소득세는 계산하지 않았습니다.",
    "금액은 연간 소득 기준의 참고 계산이며 실제 신고세액을 확정하지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    financial: financial_income_tax.Parameters   # 기본세율과 금융소득 수치
    basic_deduction: int
    wage_deduction: list        # rate x 총급여 - progressive_deduction(음수: 더하는 금액)
    wage_deduction_cap: int
    wage_credit: list
    wage_credit_limits: tuple   # (총급여 초과 기준, 기준 한도, 차감 비율, 최소 한도)
    standard_wage: int
    standard_sincere: int
    standard_other: int
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
    notes: list


def wage_deduction(params, wage):
    """제47조: 총급여액에서 빼는 근로소득공제(한도 2천만원, 총급여액을 넘지 않음)."""
    return min(apply_progressive_tax(wage, params.wage_deduction)[0], params.wage_deduction_cap, wage)


def wage_credit_limit(params, wage):
    """제59조 제2항: 총급여액 구간별 근로소득세액공제 한도."""
    tiers = sorted(params.wage_credit_limits, reverse=True)
    above, base, rate, floor = next((t for t in tiers if wage > t[0]), tiers[-1])
    return max(floor, base - truncate_won(wage - above, rate))


def _share(amount, part, whole):
    return int(Decimal(amount) * part / whole) if whole else 0


def compute(*, params, income=0, expense=0, wage_income=0, other_income=0, interest_income=0,
            non_business_interest=0, dividend_gross_up=0, dividend_other=0, withheld=True,
            personal_deduction_count=1, other_deductions=0, itemized_special_credits=False,
            sincere_business=False, other_tax_credits=0, prepaid_tax=0):
    steps, notes = [], []
    business = max(0, income - expense)
    if income or expense:
        steps.append(("사업소득금액(총수입금액-필요경비)", business))
        if expense > income:
            notes.append("필요경비가 총수입금액보다 많아 생긴 결손금은 다른 소득에서 빼지 않고 사업소득금액을 0원으로 보았습니다.")
    wage_amount = 0
    if wage_income:
        deduction = wage_deduction(params, wage_income)
        wage_amount = wage_income - deduction
        steps += [("총급여액", wage_income), ("근로소득공제", deduction), ("근로소득금액", wage_amount)]
    if other_income:
        steps.append(("그 밖의 종합소득금액(연금·기타소득 등)", other_income))
    non_financial = business + wage_amount + other_income
    deductions = params.basic_deduction * personal_deduction_count + other_deductions
    steps.append((f"종합소득공제(기본공제 {personal_deduction_count}명 포함)", deductions))

    financial = interest_income + non_business_interest + dividend_gross_up + dividend_other
    if financial:
        c = financial_income_tax.compare(
            params=params.financial, interest_income=interest_income, non_business_interest=non_business_interest,
            dividend_gross_up=dividend_gross_up, dividend_other=dividend_other, other_income=non_financial,
            income_deductions=deductions, withheld=withheld)
        steps += c.steps
        notes += c.notes
        taxable, calculated, dividend_credit, financial_prepaid = (
            c.taxable_income, c.calculated_tax, c.dividend_credit, c.prepaid)
        total_income, taxed_at_withholding = non_financial + c.included_income, c.withholding_taxed
    else:
        taxable = max(0, non_financial - deductions)
        calculated, rate = apply_progressive_tax(taxable, params.financial.brackets)
        steps += [("종합소득금액", non_financial), ("과세표준", taxable), (f"산출세액(기본세율 {rate})", calculated)]
        dividend_credit = financial_prepaid = taxed_at_withholding = 0
        total_income = non_financial

    credit_wage = 0
    if wage_income and calculated:
        # 근로소득에 대한 산출세액 = 산출세액 x 근로소득금액 / 종합소득금액(시행령 제119조의3 제1항)
        wage_tax = _share(calculated, wage_amount, total_income)
        if wage_tax != calculated:
            steps.append(("근로소득에 대한 산출세액(산출세액×근로소득금액/종합소득금액)", wage_tax))
        limit = wage_credit_limit(params, wage_income)
        credit_wage = min(apply_progressive_tax(wage_tax, params.wage_credit)[0], limit)
        steps.append((f"근로소득세액공제(총급여액 기준 한도 {limit:,}원)", credit_wage))

    # 표준세액공제와 그 밖의 세액공제는 원천징수세율 적용 금융소득분을 뺀 산출세액까지만(제61조 제2항).
    credit_base = calculated - _share(calculated, taxed_at_withholding, total_income)
    standard = 0 if itemized_special_credits else (
        params.standard_wage if wage_income else params.standard_sincere if sincere_business else params.standard_other)
    standard_applied = min(standard, credit_base)
    other_applied = min(other_tax_credits, credit_base - standard_applied)
    if standard:
        steps.append(("표준세액공제", standard_applied))
    if other_tax_credits:
        steps.append(("그 밖의 세액공제(입력값)", other_applied))
    if standard + other_tax_credits > standard_applied + other_applied:
        notes.append("표준세액공제와 그 밖의 세액공제 합계가 공제 기준 산출세액(원천징수세율로 과세된 금융소득분 제외)을 "
                     "넘어 넘는 금액은 공제하지 않았습니다(소득세법 제61조 제2항).")
    decided = max(0, calculated - dividend_credit - credit_wage - standard_applied - other_applied)
    prepaid = financial_prepaid + prepaid_tax
    balance = decided - prepaid
    prepaid_label = ("기납부세액(금융소득 원천징수 추정액 포함)" if financial_prepaid
                     else "기납부세액(금융소득 국내 원천징수 없음)" if financial and not withheld else "기납부세액")
    steps += [("결정세액", decided), (prepaid_label, prepaid),
              ("차감 납부할 세액" if balance >= 0 else "환급받을 세액", abs(balance))]
    if standard and not itemized_special_credits:
        notes.append("특별소득공제·특별세액공제를 신청하지 않은 것으로 보아 표준세액공제를 적용했습니다"
                     + ("(근로소득자 13만원)." if wage_income else
                        "(성실사업자 12만원)." if sincere_business else "(근로소득이 없는 종합소득자 7만원)."))
    if not prepaid_tax:
        notes.append("근로소득 원천징수·중간예납 등 이미 낸 세금은 입력하지 않아 0원으로 보았습니다"
                     + ("(금융소득 원천징수는 추정해 반영)." if financial_prepaid else "."))
    return Computation(steps, taxable, calculated, decided, prepaid, balance, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    financial = await financial_income_tax.load_parameters(as_of)
    rows = {name: await get_deduction("소득세", name, as_of=as_of) for name in DEDUCTION_NAMES}
    wage_bands = await get_brackets("소득세", "근로소득공제", as_of=as_of)
    credit_bands = await get_brackets("소득세", "근로소득세액공제", as_of=as_of)
    tiers = ((rows[WAGE_CREDIT_LIMIT] or {}).get("condition") or {}).get("tiers")
    if not tiers:
        raise CalculationError("missing_tax_data")
    used = [*rows.values(), *wage_bands, *credit_bands]
    return Parameters(
        financial=financial,
        basic_deduction=int(require_value(rows[BASIC], "amount")),
        wage_deduction=wage_bands, wage_deduction_cap=int(require_value(rows[WAGE_DEDUCTION_CAP], "amount")),
        wage_credit=credit_bands,
        wage_credit_limits=tuple((int(a), int(b), Decimal(str(r)), int(f)) for a, b, r, f in tiers),
        standard_wage=int(require_value(rows[STANDARD_WAGE], "amount")),
        standard_sincere=int(require_value(rows[STANDARD_SINCERE], "amount")),
        standard_other=int(require_value(rows[STANDARD_OTHER], "amount")),
        effective_dates=tuple(sorted({*financial.effective_dates,
                                      *(str(r["effective_date"]) for r in used if r and r.get("effective_date"))})),
        sources=tuple(sorted({*financial.sources,
                              *(r["source_article"] for r in used if r and r.get("source_article"))})))


async def calculate(income: int = 0, expense: int = 0, wage_income: int = 0, other_income: int = 0,
                    interest_income: int = 0, non_business_interest: int = 0, dividend_gross_up: int = 0,
                    dividend_other: int = 0, withheld: bool = True, personal_deduction_count: int = 1,
                    other_deductions: int = 0, itemized_special_credits: bool = False,
                    sincere_business: bool = False, other_tax_credits: int = 0, prepaid_tax: int = 0,
                    as_of: date | None = None) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(params=params, income=income, expense=expense, wage_income=wage_income,
                     other_income=other_income, interest_income=interest_income,
                     non_business_interest=non_business_interest, dividend_gross_up=dividend_gross_up,
                     dividend_other=dividend_other, withheld=withheld,
                     personal_deduction_count=personal_deduction_count, other_deductions=other_deductions,
                     itemized_special_credits=itemized_special_credits, sincere_business=sincere_business,
                     other_tax_credits=other_tax_credits, prepaid_tax=prepaid_tax)
    gross = income + wage_income + other_income + interest_income + non_business_interest + dividend_gross_up + dividend_other
    return CalculationResult(
        tax_type="종합소득세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / gross, 6) if gross else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

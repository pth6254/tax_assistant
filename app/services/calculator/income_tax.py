"""종합소득세 참고 계산: 소득 종류별 소득금액 → 금융소득 비교과세 → 종합소득공제 → 소득 종류별 세액공제 → 기납부세액.

소득세법 제47조(근로소득공제), 제55조(세율), 제59조(근로소득세액공제), 제59조의4 제9항(표준세액공제),
제61조(세액공제액의 한도), 제62조(금융소득 비교과세)와 시행령 제119조의3(근로소득·원천징수세율 적용
금융소득에 대한 산출세액)을 따른다. 금융소득 부분은 `financial_income_tax.compare`가 계산한다.

소득 종류별 소득금액: 사업소득은 장부(수입-경비) 또는 추계(시행령 제143조: 단순경비율, 기준경비율과 배율),
연금소득은 제47조의2 연금소득공제, 기타소득은 시행령 제87조 필요경비 의제(60%·80%)로 계산한다. 법이
납세자에게 고르게 하는 분리과세(사적연금 제14조 제3항 제9호·제64조의4, 기타소득 300만원 이하 제14조 제3항
제8호, 주택임대 2천만원 이하 제64조의2)는 가능한 조합을 모두 계산해 세금 합계가 가장 적은 쪽을 고른다.
일용근로소득(제14조 제3항 제2호)은 원천징수로 과세가 끝나므로 따로 보인다.
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
KIND_NAMES = ("연금소득공제_한도", "사적연금_분리과세_기준", "사적연금_분리과세율", "연금수령_원천징수율",
              "기타소득_분리과세_기준", "기타소득_원천징수율", "기타소득_필요경비의제_60", "기타소득_필요경비의제_80",
              "주택임대_분리과세_기준", "주택임대_분리과세", "추계_배율", "추계_복식부기_기준경비율_비율",
              "일용근로_근로소득공제", "일용근로_원천징수율", "일용근로_세액공제율", "소액부징수")
MISC_RATES = {"실제": None, "60%": "기타소득_필요경비의제_60", "80%": "기타소득_필요경비의제_80"}

SCOPE_NOTES = (
    "결손금·이월결손금, 기장세액공제, 세액감면, 가산세, 복권·종교인소득 등 그 밖의 분리과세 소득, 출자공동사업자 배당, "
    "주택임대 간주임대료, 비거주자, 국외소득의 외국납부세액공제와 지방소득세는 계산하지 않았습니다.",
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
    kinds: dict = None           # 소득 종류별 법정 수치(KIND_NAMES 행과 연금소득공제 표)
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
    total_income: int = 0
    burden: int = 0              # 결정세액 + 분리과세로 끝나는 세액(선택 비교 기준)


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


def _core(*, params, business=0, business_steps=(), wage_income=0, other_income=0, other_steps=(),
          interest_income=0, non_business_interest=0, dividend_gross_up=0, dividend_other=0, withheld=True,
          personal_deduction_count=1, other_deductions=0, itemized_special_credits=False,
          sincere_business=False, other_tax_credits=0, prepaid_tax=0, added_tax=(), extra_prepaid=0):
    """종합과세되는 소득만으로 결정세액까지. added_tax: 결정세액에 더하는 분리과세 세액(제64조의2·제64조의4)."""
    steps, notes = list(business_steps), []
    wage_amount = 0
    if wage_income:
        deduction = wage_deduction(params, wage_income)
        wage_amount = wage_income - deduction
        steps += [("총급여액", wage_income), ("근로소득공제", deduction), ("근로소득금액", wage_amount)]
    steps += list(other_steps)
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
    for label, amount in added_tax:
        steps.append((label, amount))
        decided += amount
    prepaid = financial_prepaid + prepaid_tax + extra_prepaid
    balance = decided - prepaid
    prepaid_label = ("기납부세액(원천징수 추정액 포함)" if financial_prepaid or extra_prepaid
                     else "기납부세액(금융소득 국내 원천징수 없음)" if financial and not withheld else "기납부세액")
    steps += [("결정세액", decided), (prepaid_label, prepaid),
              ("차감 납부할 세액" if balance >= 0 else "환급받을 세액", abs(balance))]
    if standard and not itemized_special_credits:
        notes.append("특별소득공제·특별세액공제를 신청하지 않은 것으로 보아 표준세액공제를 적용했습니다"
                     + ("(근로소득자 13만원)." if wage_income else
                        "(성실사업자 12만원)." if sincere_business else "(근로소득이 없는 종합소득자 7만원)."))
    if not prepaid_tax:
        notes.append("근로소득 원천징수·중간예납 등 이미 낸 세금은 입력하지 않아 0원으로 보았습니다"
                     + ("(금융소득·연금·기타소득 원천징수는 추정해 반영)." if financial_prepaid or extra_prepaid else "."))
    return Computation(steps, taxable, calculated, decided, prepaid, balance, notes, total_income, decided)


def _rate(value):
    return Decimal(str(value))


def pension_deduction(params, total):
    """제47조의2: 총연금액에서 빼는 연금소득공제(한도 900만원, 총연금액을 넘지 않음)."""
    k = params.kinds
    return min(apply_progressive_tax(total, k["연금소득공제"])[0], k["연금소득공제_한도"]["amount"], total)


def withholding_rate_by_age(params, age):
    """제129조 제1항 제5호의2: 연금수령 원천징수율(70세 미만 5%, 80세 미만 4%, 80세 이상 3%)."""
    bands = params.kinds["연금수령_원천징수율"]["condition"]["bands"]
    return _rate(next(rate for upper, rate in bands if upper is None or age <= upper))


def business_income(params, *, income, expense, method, simple_rate, simple_excess_rate, standard_rate,
                    major_expenses, double_entry):
    """사업소득금액과 그 계산 단계. 추계는 시행령 제143조 제3항(경비율은 국세청 고시 값을 입력받는다)."""
    k = params.kinds
    if method == "장부":
        steps = [("사업소득금액(총수입금액-필요경비)", max(0, income - expense))] if income or expense else []
        return max(0, income - expense), steps, []
    simple, excess = _rate(simple_rate) / 100, _rate(simple_excess_rate if simple_excess_rate is not None else simple_rate) / 100
    if method == "단순경비율":
        base = min(income, 40_000_000)
        amount = income - truncate_won(base, simple) - truncate_won(income - base, excess)
        label = (f"사업소득금액(단순경비율 {simple_rate}%" + (f", 4천만원 초과분 {simple_excess_rate}%" if
                 simple_excess_rate is not None and income > 40_000_000 else "") + ")")
        return max(0, amount), [("사업 총수입금액", income), (label, max(0, amount))], []
    if method != "기준경비율":
        raise CalculationError("unsupported_condition")
    ratio = _rate(k["추계_복식부기_기준경비율_비율"]["rate"]) if double_entry else Decimal(1)
    standard_amount = income - major_expenses - truncate_won(income, _rate(standard_rate) / 100, ratio)
    multiple = _rate(k["추계_배율"]["condition"]["double_entry" if double_entry else "simple_books"])
    compare = truncate_won(income - truncate_won(income, simple), multiple)
    amount = max(0, min(standard_amount, compare))
    steps = [("사업 총수입금액", income),
             (f"기준소득금액(수입-주요경비-수입x기준경비율 {standard_rate}%" + ("x1/2" if double_entry else "") + ")",
              max(0, standard_amount)),
             (f"비교소득금액(단순경비율 {simple_rate}% 소득금액 x 배율 {multiple})", compare),
             ("사업소득금액(둘 중 적은 금액)", amount)]
    return amount, steps, ["장부 없이 추계로 신고하면 무기장가산세(산출세액의 20%)가 붙을 수 있으며 이 계산에는 넣지 않았습니다."]


def daily_wage_tax(params, daily_wage, days):
    """일용근로소득: (일급-15만원) x 6% - 55%, 1천원 미만이면 징수하지 않음(제86조). 분리과세로 끝난다."""
    k = params.kinds
    calculated = truncate_won(max(0, daily_wage - k["일용근로_근로소득공제"]["amount"]), _rate(k["일용근로_원천징수율"]["rate"]))
    per_day = calculated - truncate_won(calculated, _rate(k["일용근로_세액공제율"]["rate"]))
    return (per_day if per_day >= k["소액부징수"]["amount"] else 0) * days


def compute(*, params, income=0, expense=0, wage_income=0, other_income=0, interest_income=0,
            non_business_interest=0, dividend_gross_up=0, dividend_other=0, withheld=True,
            personal_deduction_count=1, other_deductions=0, itemized_special_credits=False,
            sincere_business=False, other_tax_credits=0, prepaid_tax=0,
            business_method="장부", simple_rate=0, simple_excess_rate=None, standard_rate=0, major_expenses=0,
            double_entry=False, pension_income=0, private_pension=0, pension_age=0,
            misc_income=0, misc_expense_rule="실제", misc_expenses=0,
            rental_income=0, rental_expenses=0, registered_rental=False, daily_wage=0, daily_work_days=0):
    k = params.kinds
    notes = []
    business, business_steps, business_notes = business_income(
        params, income=income, expense=expense, method=business_method, simple_rate=simple_rate,
        simple_excess_rate=simple_excess_rate, standard_rate=standard_rate, major_expenses=major_expenses,
        double_entry=double_entry)
    notes += business_notes
    if business_method == "장부" and expense > income:
        notes.append("필요경비가 총수입금액보다 많아 생긴 결손금은 다른 소득에서 빼지 않고 사업소득금액을 0원으로 보았습니다.")

    # 기타소득금액 = 총수입금액 - max(실제 필요경비, 의제 필요경비)
    misc_amount = 0
    if misc_income:
        rule = MISC_RATES.get(misc_expense_rule, "invalid")
        if rule == "invalid":
            raise CalculationError("unsupported_condition")
        deemed = truncate_won(misc_income, _rate(k[rule]["rate"])) if rule else 0
        misc_amount = max(0, misc_income - max(misc_expenses, deemed))
    misc_rate = _rate(k["기타소득_원천징수율"]["rate"])
    pension_threshold = k["사적연금_분리과세_기준"]["amount"]
    age_rate = withholding_rate_by_age(params, pension_age) if private_pension else Decimal(0)
    rental_limit = k["주택임대_분리과세_기준"]["amount"]

    options = []
    private_choices = ("종합", "분리") if private_pension else ("없음",)
    misc_choices = ("종합", "분리") if 0 < misc_amount <= k["기타소득_분리과세_기준"]["amount"] else (
        ("종합",) if misc_amount else ("없음",))
    rental_choices = ("종합", "분리") if 0 < rental_income <= rental_limit else (("종합",) if rental_income else ("없음",))
    for private_choice in private_choices:
        for misc_choice in misc_choices:
            for rental_choice in rental_choices:
                options.append((private_choice, misc_choice, rental_choice))

    def run(private_choice, misc_choice, rental_choice):
        other_steps, final_steps, added, extra_prepaid = [], [], [], 0
        included_pension = pension_income + (private_pension if private_choice == "종합" else 0)
        pension_amount = 0
        if included_pension:
            deduction = pension_deduction(params, included_pension)
            pension_amount = included_pension - deduction
            other_steps += [("총연금액(종합과세)", included_pension), ("연금소득공제", deduction), ("연금소득금액", pension_amount)]
        if private_pension:
            withheld_pension = truncate_won(private_pension, age_rate)
            if private_choice == "분리" and private_pension <= pension_threshold:
                final_steps.append((f"사적연금 분리과세(원천징수 {age_rate * 100:.0f}%로 과세 종결)", withheld_pension))
            else:
                extra_prepaid += withheld_pension
                if private_choice == "분리":
                    rate = _rate(k["사적연금_분리과세율"]["rate"])
                    added.append((f"사적연금 분리과세 세액({rate * 100:.0f}%, 제64조의4)", truncate_won(private_pension, rate)))
        if misc_amount:
            withheld_misc = truncate_won(misc_amount, misc_rate)
            other_steps += [("기타소득 총수입금액", misc_income), ("기타소득금액", misc_amount)] if misc_choice == "종합" else []
            if misc_choice == "분리":
                final_steps.append((f"기타소득 분리과세(원천징수 {misc_rate * 100:.0f}%로 과세 종결)", withheld_misc))
            else:
                extra_prepaid += withheld_misc
        rental_amount = 0
        if rental_income and rental_choice == "종합":
            rental_amount = max(0, rental_income - rental_expenses)
            other_steps += [("주택임대 사업소득금액(총수입금액-필요경비)", rental_amount)]
        result = _core(params=params, business=business + rental_amount, business_steps=business_steps,
                       wage_income=wage_income, other_income=other_income + pension_amount +
                       (misc_amount if misc_choice == "종합" else 0), other_steps=other_steps + (
                           [("그 밖의 종합소득금액(입력값)", other_income)] if other_income else []),
                       interest_income=interest_income, non_business_interest=non_business_interest,
                       dividend_gross_up=dividend_gross_up, dividend_other=dividend_other, withheld=withheld,
                       personal_deduction_count=personal_deduction_count, other_deductions=other_deductions,
                       itemized_special_credits=itemized_special_credits, sincere_business=sincere_business,
                       other_tax_credits=other_tax_credits, prepaid_tax=prepaid_tax, added_tax=added,
                       extra_prepaid=extra_prepaid)
        if rental_choice == "분리":
            cond = k["주택임대_분리과세"]["condition"]
            expense_rate = _rate(cond["registered_expense_rate" if registered_rental else "expense_rate"])
            deduction = cond["registered_deduction" if registered_rental else "deduction"] if (
                result.total_income <= cond["other_income_limit"]) else 0
            rental_base = max(0, rental_income - truncate_won(rental_income, expense_rate) - deduction)
            rental_tax = truncate_won(rental_base, _rate(k["주택임대_분리과세"]["rate"]))
            # 제64조의2 제1항 제2호: 분리과세 주택임대소득 세액 + 그 외 종합소득 결정세액
            result = _core(params=params, business=business, business_steps=business_steps, wage_income=wage_income,
                           other_income=other_income + pension_amount + (misc_amount if misc_choice == "종합" else 0),
                           other_steps=other_steps + ([("그 밖의 종합소득금액(입력값)", other_income)] if other_income else []),
                           interest_income=interest_income, non_business_interest=non_business_interest,
                           dividend_gross_up=dividend_gross_up, dividend_other=dividend_other, withheld=withheld,
                           personal_deduction_count=personal_deduction_count, other_deductions=other_deductions,
                           itemized_special_credits=itemized_special_credits, sincere_business=sincere_business,
                           other_tax_credits=other_tax_credits, prepaid_tax=prepaid_tax,
                           added_tax=added + [(f"주택임대소득 분리과세 세액(({rental_income:,} - 필요경비 "
                                               f"{expense_rate * 100:.0f}% - {deduction:,}) x 14%)", rental_tax)],
                           extra_prepaid=extra_prepaid)
        final = sum(amount for _, amount in final_steps)
        result.burden = result.decided_tax + final
        return result, final_steps

    results = [(choice, *run(*choice)) for choice in options]
    # 법정 기본(분리과세)과 같은 세액이면 분리과세를 남긴다.
    choice, result, final_steps = min(results, key=lambda r: (r[1].burden, -sum(c == "분리" for c in r[0])))
    labels = {0: "사적연금", 1: "기타소득", 2: "주택임대소득"}
    for index, (picked, kinds) in enumerate(zip(choice, (private_choices, misc_choices, rental_choices))):
        if len(kinds) > 1:
            other = next(r for r in results if r[0][index] != picked and all(
                r[0][j] == choice[j] for j in range(3) if j != index))
            notes.append(f"{labels[index]}은 분리과세와 종합과세 중 선택할 수 있어 둘 다 계산했고, 세금이 "
                         f"{'적은' if other[1].burden != result.burden else '같은'} "
                         f"{'분리과세' if picked == '분리' else '종합과세'}를 골랐습니다"
                         f"(다른 쪽 세금 합계 {other[1].burden:,}원).")
    daily = daily_wage_tax(params, daily_wage, daily_work_days) if daily_wage and daily_work_days else 0
    if daily_wage and daily_work_days:
        final_steps = [*final_steps, (f"일용근로소득 원천징수(일급 {daily_wage:,}원 x {daily_work_days}일, 과세 종결)", daily)]
    if final_steps:
        result.steps += final_steps
        result.steps.append(("분리과세 포함 세금 합계(결정세액 + 분리과세 세액)",
                             result.decided_tax + sum(amount for _, amount in final_steps)))
    if rental_income and rental_income <= rental_limit and not rental_expenses:
        notes.append("주택임대 필요경비를 입력하지 않아 종합과세 쪽은 필요경비 0원으로 비교했습니다.")
    if private_pension and not pension_age:
        notes.append("연금 수령자의 나이를 입력하지 않아 사적연금 원천징수율은 70세 미만 5%로 보았습니다.")
    result.notes = notes + result.notes
    return result


async def load_parameters(as_of: date | None = None) -> Parameters:
    financial = await financial_income_tax.load_parameters(as_of)
    rows = {name: await get_deduction("소득세", name, as_of=as_of) for name in DEDUCTION_NAMES}
    kinds = {name: await get_deduction("소득세", name, as_of=as_of) for name in KIND_NAMES}
    if any(row is None for row in kinds.values()):
        raise CalculationError("missing_tax_data")
    kinds["연금소득공제"] = await get_brackets("소득세", "연금소득공제", as_of=as_of)
    wage_bands = await get_brackets("소득세", "근로소득공제", as_of=as_of)
    credit_bands = await get_brackets("소득세", "근로소득세액공제", as_of=as_of)
    tiers = ((rows[WAGE_CREDIT_LIMIT] or {}).get("condition") or {}).get("tiers")
    if not tiers:
        raise CalculationError("missing_tax_data")
    used = [*rows.values(), *wage_bands, *credit_bands, *(r for r in kinds.values() if isinstance(r, dict)),
            *kinds["연금소득공제"]]
    return Parameters(
        financial=financial,
        basic_deduction=int(require_value(rows[BASIC], "amount")),
        wage_deduction=wage_bands, wage_deduction_cap=int(require_value(rows[WAGE_DEDUCTION_CAP], "amount")),
        wage_credit=credit_bands,
        wage_credit_limits=tuple((int(a), int(b), Decimal(str(r)), int(f)) for a, b, r, f in tiers),
        standard_wage=int(require_value(rows[STANDARD_WAGE], "amount")),
        standard_sincere=int(require_value(rows[STANDARD_SINCERE], "amount")),
        standard_other=int(require_value(rows[STANDARD_OTHER], "amount")),
        kinds=kinds,
        effective_dates=tuple(sorted({*financial.effective_dates,
                                      *(str(r["effective_date"]) for r in used if r and r.get("effective_date"))})),
        sources=tuple(sorted({*financial.sources,
                              *(r["source_article"] for r in used if r and r.get("source_article"))})))


async def calculate(income: int = 0, expense: int = 0, wage_income: int = 0, other_income: int = 0,
                    interest_income: int = 0, non_business_interest: int = 0, dividend_gross_up: int = 0,
                    dividend_other: int = 0, withheld: bool = True, personal_deduction_count: int = 1,
                    other_deductions: int = 0, itemized_special_credits: bool = False,
                    sincere_business: bool = False, other_tax_credits: int = 0, prepaid_tax: int = 0,
                    business_method: str = "장부", simple_rate: float = 0, simple_excess_rate: float | None = None,
                    standard_rate: float = 0, major_expenses: int = 0, double_entry: bool = False,
                    pension_income: int = 0, private_pension: int = 0, pension_age: int = 0, misc_income: int = 0,
                    misc_expense_rule: str = "실제", misc_expenses: int = 0, rental_income: int = 0,
                    rental_expenses: int = 0, registered_rental: bool = False, daily_wage: int = 0,
                    daily_work_days: int = 0, as_of: date | None = None) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(params=params, income=income, expense=expense, wage_income=wage_income,
                     other_income=other_income, interest_income=interest_income,
                     non_business_interest=non_business_interest, dividend_gross_up=dividend_gross_up,
                     dividend_other=dividend_other, withheld=withheld,
                     personal_deduction_count=personal_deduction_count, other_deductions=other_deductions,
                     itemized_special_credits=itemized_special_credits, sincere_business=sincere_business,
                     other_tax_credits=other_tax_credits, prepaid_tax=prepaid_tax, business_method=business_method,
                     simple_rate=simple_rate, simple_excess_rate=simple_excess_rate, standard_rate=standard_rate,
                     major_expenses=major_expenses, double_entry=double_entry, pension_income=pension_income,
                     private_pension=private_pension, pension_age=pension_age, misc_income=misc_income,
                     misc_expense_rule=misc_expense_rule, misc_expenses=misc_expenses, rental_income=rental_income,
                     rental_expenses=rental_expenses, registered_rental=registered_rental, daily_wage=daily_wage,
                     daily_work_days=daily_work_days)
    gross = (income + wage_income + other_income + interest_income + non_business_interest + dividend_gross_up
             + dividend_other + pension_income + private_pension + misc_income + rental_income + daily_wage * daily_work_days)
    return CalculationResult(
        tax_type="종합소득세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / gross, 6) if gross else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

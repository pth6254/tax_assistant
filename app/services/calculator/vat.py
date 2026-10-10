"""부가가치세 참고 계산(과세기간 1회 신고분).

일반과세자: 매출세액(과세 공급가액 x 10%, 영세율 0%) - 매입세액(공제받는 매입 + 의제매입세액 - 공통매입 중
면세분) - 신용카드매출전표등 발행세액공제 - 전자신고세액공제 - 예정고지·예정신고 미환급세액.
간이과세자: 공급대가 x 업종별 부가가치율 x 10% - 매입 공급대가 x 0.5% - 신용카드매출전표등 발행세액공제
- 전자신고세액공제(공제 합계는 납부세액 한도) - 예정부과세액, 연 공급대가 4,800만원 미만이면 납부의무 면제.

부가가치세법 제30조·제37조·제38조·제39조·제40조(공통매입세액 안분)·제42조(의제매입세액)·제46조(신용카드
발행세액공제)·제63조·제69조, 시행령 제84조·제111조, 조세특례제한법 제104조의8을 따른다. 산식은 국세청
「2022년 확정 부가가치세 신고서 작성방법」 일반과세자 6개·간이과세자 4개 업종 사례로 검증한다
(tests/data/nts_vat.json). 법정 수치는 DB에서 읽는다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

CARD, SIMPLE_INPUT, EXEMPTION = "신용카드매출전표등발행세액공제", "간이과세_매입세액공제율", "간이과세_납부의무면제"
SIMPLE_RATES, DEEMED, E_FILING = "간이과세_부가가치율", "의제매입세액_음식점_개인", "전자신고세액공제"
BUSINESS_TYPES = ("소매업", "음식점업", "제조업", "농업·임업·어업", "숙박업", "건설업", "운수·창고업", "정보통신업",
                  "부동산임대업", "서비스업")

SCOPE_NOTES = (
    "과세표준(간주임대료·간주공급 등 포함)과 공제받는 매입은 입력값을 그대로 썼습니다. 대손세액, 재고매입세액, "
    "음식점 개인사업자 외의 의제매입세액, 소규모 개인사업자 감면, 겸영 간이과세자와 가산세는 계산하지 않았습니다.",
    "신용카드매출전표등 발행세액공제는 연간 한도 안에서 이번 신고까지 이미 받은 공제를 뺀 금액만큼 적용합니다.",
)


@dataclass(frozen=True)
class Parameters:
    vat_rate: Decimal
    card_rate: Decimal
    card_cap: int
    simple_rates: dict
    simple_input_rate: Decimal
    exemption_threshold: int
    deemed: dict | None          # {"rates": [[상한, "9/109"], ...], "limits": [[상한, "0.75"], ...]}
    e_filing_credit: int
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    notes: list


def _band(bands, amount):
    return next(value for upper, value in bands if upper is None or amount <= upper)


def deemed_input_tax(params, taxable_supply, purchases):
    """제42조·시행령 제84조: 음식점업 개인사업자의 면세농산물 의제매입세액(과세표준 비율 한도)."""
    if params.deemed is None:
        raise CalculationError("unsupported_condition")
    rate = Fraction(_band(params.deemed["rates"], taxable_supply))
    limit = int(taxable_supply * Decimal(_band(params.deemed["limits"], taxable_supply)))
    return int(min(purchases, limit) * rate), rate, limit


def compute(*, params, sales, purchases=0, exempt_sales=0, is_simplified=False, business_type="소매업",
            zero_rated_sales=0, common_purchases=0, non_deductible_purchases=0, deemed_purchases=0,
            card_sales=0, card_credit_eligible=True, card_credit_used=0, e_filing=False, prepaid_tax=0):
    if zero_rated_sales + exempt_sales > sales:
        raise CalculationError("invalid_input")
    notes, steps = [], []
    card_cap_left = max(0, params.card_cap - card_credit_used)
    card_credit = min(truncate_won(card_sales, params.card_rate), card_cap_left) if card_credit_eligible else 0
    if is_simplified:
        if business_type not in params.simple_rates:
            raise CalculationError("unsupported_condition")
        if zero_rated_sales or common_purchases or deemed_purchases or non_deductible_purchases:
            raise CalculationError("invalid_input")
        supply = sales - exempt_sales
        value_added = Decimal(params.simple_rates[business_type])
        payable = truncate_won(supply, value_added, params.vat_rate)
        steps += [("공급대가(부가가치세 포함)", supply),
                  (f"납부세액({business_type} 부가가치율 {value_added * 100:.0f}% x {params.vat_rate * 100:.0f}%)", payable)]
        if supply < params.exemption_threshold:
            notes.append(f"연간 공급대가가 {params.exemption_threshold:,}원 미만이어서 납부의무가 면제됩니다(제69조).")
            steps.append(("납부의무 면제(공급대가 4,800만원 미만)", payable))
            steps.append(("차감 납부할 세액", 0))
            return Computation(steps, supply, payable, 0, notes)
        input_credit = truncate_won(purchases, params.simple_input_rate)
        credits = [("매입세금계산서등 수취세액공제(매입 공급대가 x 0.5%)", input_credit),
                   ("신용카드매출전표등 발행세액공제", card_credit),
                   ("전자신고세액공제", params.e_filing_credit if e_filing else 0)]
        total_credit = min(payable, sum(amount for _, amount in credits))
        steps += [(label, amount) for label, amount in credits if amount]
        if total_credit < sum(amount for _, amount in credits):
            notes.append("간이과세자의 공제세액 합계는 납부세액을 넘을 수 없어 넘는 금액은 공제하지 않았습니다(환급 없음).")
        decided = payable - total_credit - prepaid_tax
        if prepaid_tax:
            steps.append(("예정부과(신고)세액", prepaid_tax))
        steps.append(("차감 납부할 세액" if decided >= 0 else "환급받을 세액", abs(decided)))
        return Computation(steps, supply, payable, decided, notes)

    taxable = sales - zero_rated_sales - exempt_sales
    output = truncate_won(taxable, params.vat_rate)
    steps += [("과세 공급가액(10%)", taxable)]
    if zero_rated_sales:
        steps.append(("영세율 공급가액(0%)", zero_rated_sales))
    steps.append(("매출세액", output))
    deductible = purchases + common_purchases - non_deductible_purchases
    if deductible < 0:
        raise CalculationError("invalid_input")
    common_exempt = 0
    if common_purchases and exempt_sales:
        # 공통매입세액 중 면세사업분: 면세공급가액 / 총공급가액 비율(제40조, 시행령 제81조)
        common_exempt = int(Decimal(common_purchases) * exempt_sales / sales)
        steps.append((f"공통매입 중 면세사업분(면세공급가액 비율 {exempt_sales / sales:.2%})", common_exempt))
    input_tax = truncate_won(deductible - common_exempt, params.vat_rate)
    steps.append(("공제받는 매입세액(세금계산서·신용카드 등)", input_tax))
    deemed = 0
    if deemed_purchases:
        deemed, rate, limit = deemed_input_tax(params, taxable, deemed_purchases)
        steps.append((f"의제매입세액(면세농산물 {min(deemed_purchases, limit):,}원 x {rate.numerator}/{rate.denominator})", deemed))
        if deemed_purchases > limit:
            notes.append(f"면세농산물 매입액이 과세표준 기준 한도({limit:,}원)를 넘어 한도까지만 의제매입세액을 계산했습니다.")
    payable = output - input_tax - deemed
    steps.append(("납부(환급)세액(매출세액 - 매입세액)", payable))
    if card_credit:
        steps.append(("신용카드매출전표등 발행세액공제", card_credit))
    e_credit = params.e_filing_credit if e_filing else 0
    if e_credit:
        steps.append(("전자신고세액공제", e_credit))
    # 경감·공제세액은 납부세액을 한도로 한다(제46조 제1항, 환급세액을 만들지 않음).
    credit = min(card_credit + e_credit, max(0, payable))
    if prepaid_tax:
        steps.append(("예정고지세액·예정신고 미환급세액", prepaid_tax))
    decided = payable - credit - prepaid_tax
    steps.append(("차감 납부할 세액" if decided >= 0 else "환급받을 세액", abs(decided)))
    if not card_credit_eligible and card_sales:
        notes.append("법인과 직전 연도 공급가액 10억원 초과 개인사업자는 신용카드매출전표등 발행세액공제를 받지 못합니다.")
    return Computation(steps, taxable, output, decided, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    rows = {name: await get_deduction("부가가치세", name, as_of=as_of)
            for name in (CARD, SIMPLE_INPUT, EXEMPTION, SIMPLE_RATES, E_FILING)}
    try:
        rows[DEEMED] = await get_deduction("부가가치세", DEEMED, as_of=as_of)
    except CalculationError as exc:
        if exc.code != "missing_tax_data":
            raise
        rows[DEEMED] = None
    brackets = await get_brackets("부가가치세", "default", as_of=as_of)
    rates = ((rows[SIMPLE_RATES] or {}).get("condition") or {}).get("rates")
    if not brackets or not rates:
        raise CalculationError("missing_tax_data")
    used = [r for r in [*rows.values(), *brackets] if r]
    return Parameters(
        vat_rate=Decimal(str(require_value(brackets[0], "rate"))),
        card_rate=Decimal(str(require_value(rows[CARD], "rate"))),
        card_cap=int(require_value(rows[CARD], "max_amount")),
        simple_rates=rates, simple_input_rate=Decimal(str(require_value(rows[SIMPLE_INPUT], "rate"))),
        exemption_threshold=int(require_value(rows[EXEMPTION], "amount")),
        deemed=(rows[DEEMED] or {}).get("condition") or None,
        e_filing_credit=int(require_value(rows[E_FILING], "amount")),
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r.get("source_article")})))


async def calculate(sales: int, purchases: int = 0, exempt_sales: int = 0, is_simplified: bool = False,
                    business_type: str = "소매업", zero_rated_sales: int = 0, common_purchases: int = 0,
                    non_deductible_purchases: int = 0, deemed_purchases: int = 0, card_sales: int = 0,
                    card_credit_eligible: bool = True, card_credit_used: int = 0, e_filing: bool = False,
                    prepaid_tax: int = 0, as_of: date | None = None) -> CalculationResult:
    if is_simplified and business_type not in BUSINESS_TYPES:
        raise CalculationError("unsupported_condition")
    params = await load_parameters(as_of)
    result = compute(params=params, sales=sales, purchases=purchases, exempt_sales=exempt_sales,
                     is_simplified=is_simplified, business_type=business_type, zero_rated_sales=zero_rated_sales,
                     common_purchases=common_purchases, non_deductible_purchases=non_deductible_purchases,
                     deemed_purchases=deemed_purchases, card_sales=card_sales,
                     card_credit_eligible=card_credit_eligible, card_credit_used=card_credit_used,
                     e_filing=e_filing, prepaid_tax=prepaid_tax)
    return CalculationResult(
        tax_type="부가가치세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / sales, 6) if sales else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

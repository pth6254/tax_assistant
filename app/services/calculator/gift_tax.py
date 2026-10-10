"""증여세 참고 계산: 증여재산가액 → 채무·10년 내 동일인 증여 가산 → 증여재산공제 → 세율 → 세대생략 할증
→ 기납부세액공제 → 신고세액공제.

상속세 및 증여세법 제47조(과세가액, 동일인 10년 합산), 제53조(증여재산공제, 관계별 10년 한도),
제53조의2(혼인·출산 증여재산공제), 제55조(과세표준·과세최저한), 제56조(세율), 제57조(세대생략 할증),
제58조(납부세액공제), 제69조(신고세액공제)를 따른다. 산식은 국세청 증여세 신고서 작성 사례와
「2026 세금절약가이드 Ⅱ」 사례로 검증한다(tests/data/nts_gift_tax.json). 법정 수치는 DB에서 읽는다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일의 수치를 읽어 호출한다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

RELATIONS = ("배우자", "직계존비속", "기타친족", "기타")
DEDUCTION_NAMES = {"배우자": "증여재산공제_배우자", "직계존비속": "증여재산공제_직계존비속",
                   "기타친족": "증여재산공제_기타친족"}
MINOR = "증여재산공제_직계존비속_미성년"
MARRIAGE_BIRTH = "증여재산공제_혼인출산"
SURCHARGE, SURCHARGE_LARGE = "세대생략할증률", "세대생략할증률_미성년_고액"
FILING_CREDIT, MINIMUM = "신고세액공제율", "과세최저한"

SCOPE_NOTES = (
    "증여재산가액은 시가 등으로 평가된 금액을 입력받으며 재산 평가는 하지 않았습니다. 합산배제 증여재산, "
    "창업자금·가업승계 특례, 영농자녀 감면, 비거주자, 외국납부세액공제와 가산세는 계산하지 않았습니다.",
    "금액은 증여 1건 기준의 참고 계산이며 실제 신고세액을 확정하지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    brackets: list
    deductions: dict           # 관계(직계존비속 미성년은 "미성년") → 10년 공제 한도
    marriage_birth: int | None  # None: 기준일에 혼인·출산 공제가 없음
    surcharge_rate: Decimal
    surcharge_large_rate: Decimal
    surcharge_large_threshold: int
    filing_credit_rate: Decimal
    minimum: int
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    notes: list


def _tax(params, taxable):
    return apply_progressive_tax(taxable, params.brackets)[0] if taxable >= params.minimum else 0


def compute(*, params, gift_amount, relation="기타", is_minor=False, debts=0, prior_gifts_10y=0,
            prior_gift_tax=0, prior_gift_taxable=0, deduction_used_10y=0, marriage_birth=False,
            marriage_birth_used=0, generation_skipping=False, filed_on_time=True):
    if relation not in RELATIONS:
        raise CalculationError("unsupported_condition")
    if debts > gift_amount or (generation_skipping or marriage_birth) and relation != "직계존비속":
        raise CalculationError("invalid_input")
    notes = []
    base = gift_amount - debts + prior_gifts_10y
    steps = [("증여재산가액", gift_amount)]
    if debts:
        steps.append(("인수한 채무액(부담부증여)", debts))
        notes.append("수증자가 인수한 채무 부분은 증여자가 양도한 것으로 보아 증여자에게 양도소득세가 따로 과세될 수 있습니다.")
    if prior_gifts_10y:
        steps.append(("증여재산가산액(10년 내 동일인 증여)", prior_gifts_10y))
    steps.append(("증여세 과세가액", base))

    # 증여재산공제는 관계별로 10년간 한도 안에서 공제한다(이미 다른 증여에 쓴 공제를 뺀다).
    limit = 0 if relation == "기타" else params.deductions["미성년" if relation == "직계존비속" and is_minor else relation]
    deduction = min(max(0, limit - deduction_used_10y), base)
    steps.append((f"증여재산공제({relation}{', 미성년' if relation == '직계존비속' and is_minor else ''})", deduction))
    if marriage_birth:
        if params.marriage_birth is None:
            raise CalculationError("unsupported_condition")
        extra = min(max(0, params.marriage_birth - marriage_birth_used), base - deduction)
        steps.append(("혼인·출산 증여재산공제", extra))
        deduction += extra
    taxable = base - deduction
    steps.append(("증여세 과세표준", taxable))
    calculated, rate = apply_progressive_tax(taxable, params.brackets)
    if taxable < params.minimum:
        calculated = 0
        notes.append(f"과세표준이 {params.minimum:,}원 미만이어서 증여세를 부과하지 않습니다(과세최저한).")
    steps.append((f"증여세 산출세액(세율 {rate})", calculated))

    surcharge = 0
    if generation_skipping:
        large = is_minor and gift_amount > params.surcharge_large_threshold
        surcharge = truncate_won(calculated, params.surcharge_large_rate if large else params.surcharge_rate)
        steps.append((f"세대생략 할증과세액({'40' if large else '30'}%)", surcharge))
    total = calculated + surcharge

    paid_credit = 0
    if prior_gifts_10y:
        estimated = not (prior_gift_tax or prior_gift_taxable)
        if estimated:
            # 이전 증여만으로 계산했을 때의 과세표준·산출세액(현행 세율·공제로 추정).
            prior_taxable = max(0, prior_gifts_10y - min(max(0, limit - deduction_used_10y), prior_gifts_10y))
            prior_gift_taxable, prior_gift_tax = prior_taxable, _tax(params, prior_taxable)
            notes.append("가산한 이전 증여의 과세표준·산출세액은 입력이 없어 현행 세율과 같은 증여재산공제로 다시 계산한 "
                         "추정치를 썼습니다. 당시 신고서의 금액을 입력하면 정확해집니다.")
        cap = int(Decimal(total) * prior_gift_taxable / taxable) if taxable else 0
        paid_credit = min(prior_gift_tax, cap)
        steps.append((f"기납부세액공제(이전 증여 산출세액 {prior_gift_tax:,}원과 한도 {cap:,}원 중 작은 금액)", paid_credit))
    filing = truncate_won(total - paid_credit, params.filing_credit_rate) if filed_on_time else 0
    steps.append(("신고세액공제(3%)" if filed_on_time else "신고세액공제(기한 내 신고 아님)", filing))
    decided = max(0, total - paid_credit - filing)
    steps.append(("납부할 세액", decided))
    if generation_skipping:
        notes.append("증여자의 자녀(수증자의 부모)가 살아 있어 세대생략 할증을 적용했습니다. 부모가 사망해 손자녀가 받으면 할증하지 않습니다.")
    if filed_on_time:
        notes.append("증여일이 속하는 달의 말일부터 3개월 안에 신고하는 것으로 보아 신고세액공제 3%를 적용했습니다.")
    return Computation(steps, taxable, calculated, decided, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    names = [*DEDUCTION_NAMES.values(), MINOR, SURCHARGE, SURCHARGE_LARGE, FILING_CREDIT, MINIMUM]
    rows = {name: await get_deduction("증여세", name, as_of=as_of) for name in names}
    try:
        rows[MARRIAGE_BIRTH] = await get_deduction("증여세", MARRIAGE_BIRTH, as_of=as_of)
    except CalculationError as exc:
        if exc.code != "missing_tax_data":
            raise
        rows[MARRIAGE_BIRTH] = None   # 2024년 전 증여에는 혼인·출산 공제가 없다.
    brackets = await get_brackets("증여세", "default", as_of=as_of)
    used = [r for r in [*rows.values(), *brackets] if r]
    deductions = {relation: int(require_value(rows[name], "amount")) for relation, name in DEDUCTION_NAMES.items()}
    deductions["미성년"] = int(require_value(rows[MINOR], "amount"))
    return Parameters(
        brackets=brackets, deductions=deductions,
        marriage_birth=int(require_value(rows[MARRIAGE_BIRTH], "amount")) if rows[MARRIAGE_BIRTH] else None,
        surcharge_rate=Decimal(str(require_value(rows[SURCHARGE], "rate"))),
        surcharge_large_rate=Decimal(str(require_value(rows[SURCHARGE_LARGE], "rate"))),
        surcharge_large_threshold=int(require_value(rows[SURCHARGE_LARGE], "amount")),
        filing_credit_rate=Decimal(str(require_value(rows[FILING_CREDIT], "rate"))),
        minimum=int(require_value(rows[MINIMUM], "amount")),
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r.get("source_article")})))


async def calculate(gift_amount: int, relation: str = "기타", is_minor: bool = False, prior_gifts_10y: int = 0,
                    debts: int = 0, prior_gift_tax: int = 0, prior_gift_taxable: int = 0, deduction_used_10y: int = 0,
                    marriage_birth: bool = False, marriage_birth_used: int = 0, generation_skipping: bool = False,
                    filed_on_time: bool = True, as_of: date | None = None) -> CalculationResult:
    if relation not in RELATIONS:
        raise CalculationError("unsupported_condition")
    params = await load_parameters(as_of)
    result = compute(params=params, gift_amount=gift_amount, relation=relation, is_minor=is_minor, debts=debts,
                     prior_gifts_10y=prior_gifts_10y, prior_gift_tax=prior_gift_tax,
                     prior_gift_taxable=prior_gift_taxable, deduction_used_10y=deduction_used_10y,
                     marriage_birth=marriage_birth, marriage_birth_used=marriage_birth_used,
                     generation_skipping=generation_skipping, filed_on_time=filed_on_time)
    return CalculationResult(
        tax_type="증여세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / gift_amount, 6) if gift_amount else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

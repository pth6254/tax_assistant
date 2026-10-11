"""국세 신고·납부 가산세 참고 계산: 무신고·과소신고 가산세(감면 반영) + 납부지연가산세.

국세기본법 제47조의2(무신고: 20%, 부정 40%, 복식부기의무자·법인은 수입금액 1만분의 7·14 하한),
제47조의3(과소신고: 10%, 부정 40%), 제47조의4·시행령 제27조의4(납부지연: 1일 10만분의 22),
제48조 제2항(수정신고 90~10%, 기한 후 신고 50~20% 감면)을 따른다. 산식은 국세청 「2026 세금절약가이드」의
무신고 사례와 종합소득세 신고서 작성사례의 무신고가산세로 검증한다(tests/data/nts_penalty.json).
법정 수치는 DB에서 읽는다.

`penalty_type`이 무신고·과소신고이면 신고 가산세와 (지연일수가 있으면) 납부지연가산세를 함께 계산하고,
납부지연이면 납부지연가산세만 계산한다. 세목 계산기는 `attach`로 자기 결과에 같은 계산을 옵션으로 붙인다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, PenaltyOption, TaxBasis, TaxStep
from app.services.calculator.brackets import truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_deduction

TYPES = ("무신고", "과소신고", "납부지연")
RATE_NAMES = {"무신고": "무신고가산세_일반", "무신고_부정": "무신고가산세_부정", "과소신고": "과소신고가산세_일반",
              "과소신고_부정": "과소신고가산세_부정", "수입금액": "무신고가산세_수입금액_일반",
              "수입금액_부정": "무신고가산세_수입금액_부정"}
ZERO_RATED = "영세율과세표준_불성실"
DAILY, AMENDED, LATE_RETURN = "납부지연가산세_일률", "수정신고_감면", "기한후신고_감면"

SCOPE_NOTES = (
    "납부고지서를 받은 뒤 지정납부기한까지 내지 않을 때의 3% 가산세와 그 이후 기간, 원천징수 등 납부지연가산세, "
    "세금계산서·지급명세서 등 개별 세법의 가산세는 계산하지 않았습니다.",
    "가산세 감면은 세무서가 결정·경정할 것을 미리 알고 신고한 경우에는 적용되지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    rates: dict
    daily_rate: Decimal
    amended_bands: list
    late_return_bands: list
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    notes: list


def reduction_rate(bands, months):
    """제48조 제2항: 법정신고기한이 지난 뒤 몇 개월 안에 신고했는지에 따른 감면율(없으면 0)."""
    if not months:
        return Decimal(0)
    return next((Decimal(rate) for upper, rate in bands if months <= upper), Decimal(0))


def compute(*, params, unpaid_tax, penalty_type="무신고", is_negligent=False, days_late=0,
            filed_within_months=0, revenue=0, zero_rated_base=0):
    """zero_rated_base: 무신고·과소신고된 부가가치세 영세율과세표준(제47조의2 제2항·제47조의3 제2항, 1천분의 5)."""
    if penalty_type not in TYPES:
        raise CalculationError("unsupported_condition")
    if penalty_type == "납부지연" and (is_negligent or filed_within_months or revenue or zero_rated_base):
        raise CalculationError("invalid_input")
    steps = [("본세(신고하지 않았거나 덜 낸 세액)", unpaid_tax)]
    notes = []
    filing = 0
    if penalty_type != "납부지연":
        key = penalty_type + ("_부정" if is_negligent else "")
        rate = params.rates[key]
        filing = truncate_won(unpaid_tax, rate)
        label = f"{penalty_type}가산세({rate * 100:.0f}%{' · 부정행위' if is_negligent else ''})"
        if revenue and (penalty_type == "무신고" or is_negligent):
            # 복식부기의무자·법인: 세액 기준과 수입금액 기준 중 큰 금액(부정 과소신고는 부정분 수입금액 기준).
            revenue_rate = params.rates["수입금액_부정" if is_negligent else "수입금액"]
            by_revenue = truncate_won(revenue, revenue_rate)
            if by_revenue > filing:
                filing = by_revenue
                label = f"{penalty_type}가산세(수입금액 {revenue:,}원 x {revenue_rate * 10000:.0f}/10,000)"
        steps.append((label, filing))
        if zero_rated_base:
            zero_rate = params.rates.get("영세율")
            if zero_rate is None:
                raise CalculationError("missing_tax_data")
            zero = truncate_won(zero_rated_base, zero_rate)
            steps.append((f"영세율과세표준 신고불성실가산세({zero_rated_base:,}원 x {zero_rate * 1000:.0f}/1,000)", zero))
            filing += zero
        bands = params.late_return_bands if penalty_type == "무신고" else params.amended_bands
        reduction = truncate_won(filing, reduction_rate(bands, filed_within_months))
        if reduction:
            kind = "기한 후 신고" if penalty_type == "무신고" else "수정신고"
            steps.append((f"{kind} 감면({filed_within_months}개월 이내, {reduction_rate(bands, filed_within_months) * 100:.0f}%)",
                          reduction))
            filing -= reduction
        elif filed_within_months:
            notes.append("법정신고기한이 지난 뒤 감면 기간(기한 후 신고 6개월, 수정신고 2년)을 넘겨 신고해 감면이 없습니다.")
    late = truncate_won(unpaid_tax, params.daily_rate, days_late)
    if days_late or penalty_type == "납부지연":
        steps.append((f"납부지연가산세(1일 {params.daily_rate * 100:.3f}% x {days_late}일)", late))
    penalty = filing + late
    steps += [("가산세 합계", penalty), ("납부할 총액(본세+가산세)", unpaid_tax + penalty)]
    if penalty_type != "납부지연" and not days_late:
        notes.append("납부지연 일수를 입력하지 않아 납부지연가산세는 0원으로 보았습니다. 법정납부기한 다음 날부터 "
                     "낸 날까지 하루 0.022%가 붙습니다.")
    return Computation(steps, unpaid_tax, penalty, unpaid_tax + penalty, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    rows = {key: await get_deduction("가산세", name, as_of=as_of) for key, name in RATE_NAMES.items()}
    try:
        zero_rated = await get_deduction("가산세", ZERO_RATED, as_of=as_of)
    except CalculationError as exc:
        if exc.code != "missing_tax_data":
            raise
        zero_rated = None
    for name in (DAILY, AMENDED, LATE_RETURN):
        rows[name] = await get_deduction("가산세", name, as_of=as_of)
    daily = ((rows[DAILY] or {}).get("condition") or {}).get("daily_rate")
    amended = ((rows[AMENDED] or {}).get("condition") or {}).get("bands")
    late_return = ((rows[LATE_RETURN] or {}).get("condition") or {}).get("bands")
    if not (daily and amended and late_return):
        raise CalculationError("missing_tax_data")
    used = [r for r in rows.values() if r]
    return Parameters(
        rates={**{key: Decimal(str(require_value(rows[key], "rate"))) for key in RATE_NAMES},
               **({"영세율": Decimal(str(zero_rated["rate"]))} if zero_rated and zero_rated.get("rate") is not None else {})},
        daily_rate=Decimal(daily), amended_bands=amended, late_return_bands=late_return,
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r.get("source_article")})))


OPTION_FIELDS = tuple(PenaltyOption.model_fields)
BASE_LABELS = {"무신고": "가산세 대상 세액(신고하지 않은 납부할 세액)",
               "과소신고": "가산세 대상 세액(바른 납부할 세액 {base:,}원 - 신고한 세액 {reported:,}원)",
               "납부지연": "미납세액(납부할 세액 {base:,}원 - 이미 낸 세액 {reported:,}원)"}


def penalty_option(options):
    """The penalty fields of a calculator request, split from its own inputs."""
    return {key: options.pop(key) for key in OPTION_FIELDS if key in options}


async def attach(result: CalculationResult, base_tax: int, *, penalty_type: str = "없음", reported_tax: int = 0,
                 is_negligent: bool = False, days_late: int = 0, filed_within_months: int = 0,
                 penalty_revenue: int = 0, zero_rated_base: int = 0, as_of: date | None = None) -> CalculationResult:
    """세목 계산 결과에 가산세 옵션을 붙인다. base_tax는 그 세목의 납부할 세액(기납부세액 차감 후)."""
    if penalty_type == "없음":
        if reported_tax or is_negligent or days_late or filed_within_months or penalty_revenue:
            raise CalculationError("invalid_input")
        return result
    if penalty_type == "무신고" and reported_tax:
        raise CalculationError("invalid_input")
    if penalty_type == "납부지연" and penalty_revenue:
        raise CalculationError("invalid_input")
    unpaid = max(0, base_tax - reported_tax)
    params = await load_parameters(as_of)
    penalty = compute(params=params, unpaid_tax=unpaid, penalty_type=penalty_type, is_negligent=is_negligent,
                      days_late=days_late, filed_within_months=filed_within_months, revenue=penalty_revenue,
                      zero_rated_base=zero_rated_base if penalty_type != "납부지연" else 0)
    steps = list(penalty.steps)
    steps[0] = (BASE_LABELS[penalty_type].format(base=base_tax, reported=reported_tax), unpaid)
    if penalty_type != "무신고":
        steps[-1] = ("추가로 낼 금액(덜 낸 세액 + 가산세)", penalty.decided_tax)
    result.steps += [TaxStep(label=label, amount=amount) for label, amount in steps]
    result.final_tax = penalty.decided_tax
    result.source_articles = [*result.source_articles, *(s for s in params.sources if s not in result.source_articles)]
    if result.basis:
        result.basis.effective_dates = sorted({*result.basis.effective_dates, *params.effective_dates})
    if base_tax <= 0:
        penalty.notes.append("납부할 세액이 없어(환급 포함) 세액 기준 가산세는 0원입니다.")
    result.notes = [*result.notes, *penalty.notes, *SCOPE_NOTES]
    return result


async def calculate(unpaid_tax: int, penalty_type: str = "무신고", is_negligent: bool = False, days_late: int = 0,
                    filed_within_months: int = 0, revenue: int = 0, as_of: date | None = None) -> CalculationResult:
    if penalty_type not in TYPES:
        raise CalculationError("unsupported_condition")
    params = await load_parameters(as_of)
    result = compute(params=params, unpaid_tax=unpaid_tax, penalty_type=penalty_type, is_negligent=is_negligent,
                     days_late=days_late, filed_within_months=filed_within_months, revenue=revenue)
    return CalculationResult(
        tax_type="가산세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=unpaid_tax, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.calculated_tax / unpaid_tax, 6) if unpaid_tax else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

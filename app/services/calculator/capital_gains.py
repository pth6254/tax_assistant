"""부동산(주택·토지·건물) 양도소득세 참고 계산.

소득세법 제89조 제1항 제3호(1세대 1주택 비과세, 고가주택 제외), 제95조(장기보유특별공제 표1·표2),
제103조(양도소득 기본공제), 제104조(세율, 단기보유 세율, 제7항 다주택 중과)와 시행령 제154조
(1세대 1주택 비과세 요건), 제159조의4(표2 적용 1세대 1주택), 제160조(고가주택 양도차익 안분)를 따른다.
산식은 국세청 양도소득세 신고서 작성 사례와 고가주택 계산 안내, 「2026 세금절약가이드 Ⅱ」의
세율 비교표로 검증한다(tests/data/nts_capital_gains.json). 법정 수치는 DB(tax_deductions,
tax_brackets)에서 읽는다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일(양도일)의
수치를 읽어 호출한다. 1세대 1주택 여부·취득 당시 조정대상지역 여부·중과 대상 여부는 사실관계
판단이므로 입력으로 받고, 계산기가 추정하지 않는다.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

HOUSE, LAND = "주택", "토지·건물"
ASSET_TYPES = (HOUSE, LAND)
SURCHARGES = ("없음", "2주택", "3주택이상")
# Requirements written as periods in the statute; rates and amounts come from the database.
EXEMPT_HOLDING_YEARS = 2       # 시행령 제154조 제1항
EXEMPT_RESIDENCE_YEARS = 2     # 같은 항 괄호(취득 당시 조정대상지역)·제159조의4
LTD_MIN_HOLDING_YEARS = 3      # 법 제95조 제2항

DEDUCTION_NAMES = {
    "high_price_threshold": "고가주택기준금액",
    "general_rate": "장기보유특별공제_일반_연공제율", "general_cap": "장기보유특별공제_일반_한도",
    "home_holding_rate": "장기보유특별공제_1주택_보유_연공제율", "home_holding_cap": "장기보유특별공제_1주택_보유_한도",
    "home_residence_rate": "장기보유특별공제_1주택_거주_연공제율", "home_residence_cap": "장기보유특별공제_1주택_거주_한도",
    "surcharge_two": "다주택중과_2주택", "surcharge_three": "다주택중과_3주택이상",
    "local_tax_ratio": "지방소득세_비율",
}
SHORT_RATE_CATEGORIES = {(HOUSE, 0): "주택_1년미만", (HOUSE, 1): "주택_2년미만",
                         (LAND, 0): "토지건물_1년미만", (LAND, 1): "토지건물_2년미만"}

SCOPE_NOTES = (
    "거주자의 등기된 국내 주택·토지·건물 1건을 그해 유일한 양도로 보고 계산했습니다. 비사업용 토지(세율 10%p 가산), "
    "미등기 양도, 분양권·조합원입주권, 주식, 조세특례제한법 감면, 장기임대주택 특례, 같은 해 여러 건 양도의 비교과세, "
    "전자신고세액공제는 반영하지 않았습니다.",
    "1세대 1주택·조정대상지역·다주택 중과 여부는 입력값을 따른 것이며 계산기가 사실관계를 판정하지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    brackets: list
    short_rates: dict
    basic_deduction: int
    high_price_threshold: int
    general_rate: Decimal
    general_cap: Decimal
    home_holding_rate: Decimal
    home_holding_cap: Decimal
    home_residence_rate: Decimal
    home_residence_cap: Decimal
    surcharges: dict
    local_tax_ratio: Decimal
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    local_tax: int
    method: str
    notes: list = field(default_factory=list)


def _check_inputs(asset_type, holding_years, residence_years, is_one_home, multi_home_surcharge):
    if asset_type not in ASSET_TYPES or multi_home_surcharge not in SURCHARGES:
        raise CalculationError("unsupported_condition")
    if residence_years > holding_years:
        raise CalculationError("invalid_input")
    if asset_type != HOUSE and (is_one_home or multi_home_surcharge != "없음"):
        raise CalculationError("invalid_input")
    if is_one_home and multi_home_surcharge != "없음":
        raise CalculationError("invalid_input")


def long_term_rate(params, *, holding_years, residence_years, is_one_home, surcharged):
    """(공제율, 설명) — 표2는 1세대 1주택으로 보유기간 중 2년 이상 거주한 경우(시행령 제159조의4)."""
    if surcharged:
        return Decimal(0), "다주택 중과 대상은 장기보유특별공제를 적용하지 않음"
    if holding_years < LTD_MIN_HOLDING_YEARS:
        return Decimal(0), f"보유기간 {LTD_MIN_HOLDING_YEARS}년 미만"
    if is_one_home and residence_years >= EXEMPT_RESIDENCE_YEARS:
        holding = min(params.home_holding_cap, params.home_holding_rate * holding_years)
        residence = min(params.home_residence_cap, params.home_residence_rate * residence_years)
        return holding + residence, (f"1세대 1주택 표2: 보유 {holding_years}년 {_pct(holding)} + "
                                     f"거주 {residence_years}년 {_pct(residence)}")
    rate = min(params.general_cap, params.general_rate * holding_years)
    return rate, f"표1: 보유 {holding_years}년 {_pct(rate)}"


def _pct(rate):
    return f"{(Decimal(rate) * 100).normalize():f}%"


def compute(*, params, transfer_price, acquisition_price, expenses=0, holding_years=0, asset_type=HOUSE,
            is_one_home=False, residence_years=0, acquired_in_adjusted_area=False, multi_home_surcharge="없음"):
    _check_inputs(asset_type, holding_years, residence_years, is_one_home, multi_home_surcharge)
    gain = transfer_price - acquisition_price - expenses
    steps = [("양도차익(양도가액-취득가액-필요경비)", max(0, gain))]
    notes = []
    if gain <= 0:
        notes.append("양도차익이 없어(양도차손) 납부할 양도소득세가 없습니다. 같은 해 다른 양도차익과의 통산은 계산하지 않았습니다.")
        return Computation(steps, 0, 0, 0, "no_gain", notes)

    exempt = (is_one_home and holding_years >= EXEMPT_HOLDING_YEARS
              and (not acquired_in_adjusted_area or residence_years >= EXEMPT_RESIDENCE_YEARS))
    threshold = params.high_price_threshold
    if is_one_home and not exempt:
        notes.append(f"1세대 1주택이지만 비과세 요건(보유 {EXEMPT_HOLDING_YEARS}년 이상"
                     + (f", 취득 당시 조정대상지역이면 거주 {EXEMPT_RESIDENCE_YEARS}년 이상" if acquired_in_adjusted_area else "")
                     + ")을 충족하지 않아 전체 양도차익에 과세했습니다.")
    if exempt and transfer_price <= threshold:
        steps.append((f"1세대 1주택 비과세(양도가액 {threshold:,}원 이하)", max(0, gain)))
        notes.append("1세대 1주택 비과세 요건을 충족하고 양도가액이 고가주택 기준금액 이하라 양도소득세가 없습니다.")
        return Computation(steps, 0, 0, 0, "exempt", notes)

    surcharged = multi_home_surcharge != "없음"
    rate, rate_text = long_term_rate(params, holding_years=holding_years, residence_years=residence_years,
                                     is_one_home=is_one_home, surcharged=surcharged)
    full_deduction = truncate_won(gain, rate)
    if exempt:
        # 시행령 제160조: 12억원 초과분만 과세 — 양도차익과 장기보유특별공제를 같은 비율로 안분한다.
        taxable_gain = gain * (transfer_price - threshold) // transfer_price
        deduction = full_deduction * (transfer_price - threshold) // transfer_price
        steps.append((f"고가주택 과세대상 양도차익(×(양도가액-{threshold:,})/양도가액)", taxable_gain))
        steps.append((f"장기보유특별공제({rate_text}, 고가주택 안분)", deduction))
        notes.append("1세대 1주택 고가주택이라 양도가액 중 고가주택 기준금액을 넘는 비율만큼만 과세했습니다.")
    else:
        taxable_gain, deduction = gain, full_deduction
        steps.append((f"장기보유특별공제({rate_text})", deduction))
    income = taxable_gain - deduction
    basic = min(income, params.basic_deduction)
    taxable = income - basic
    steps += [("양도소득금액", income), ("양도소득 기본공제", basic), ("과세표준", taxable)]

    base_tax, base_rate = apply_progressive_tax(taxable, params.brackets)
    candidates = [(base_tax, f"기본세율 {base_rate}")]
    if surcharged:
        extra = params.surcharges[multi_home_surcharge]
        candidates = [(base_tax + truncate_won(taxable, extra), f"기본세율 {base_rate} + 중과 {_pct(extra)}p")]
    if holding_years < 2:
        short = params.short_rates[(asset_type, holding_years)]
        candidates.append((truncate_won(taxable, short),
                           f"{'1년 미만' if holding_years == 0 else '1년 이상 2년 미만'} 보유 {_pct(short)}"))
    calculated, rate_label = max(candidates, key=lambda c: c[0])
    if len(candidates) > 1:
        notes.append("한 자산에 둘 이상의 세율이 해당하면 그중 큰 세액을 적용합니다(제104조 제1항·제7항): "
                     + ", ".join(f"{label} {tax:,}원" for tax, label in candidates) + ".")
    local = truncate_won(calculated, params.local_tax_ratio)
    steps += [(f"산출세액({rate_label})", calculated),
              (f"지방소득세(별도 납부, 산출세액의 {_pct(params.local_tax_ratio)})", local),
              ("양도소득세와 지방소득세 합계", calculated + local)]
    if surcharged:
        notes.append(f"조정대상지역 다주택 중과({multi_home_surcharge})를 입력대로 적용했습니다. 중과 배제 주택이거나 "
                     "중과 한시 배제 기간(2022-05-10~2026-05-09 양도, 2년 이상 보유)에 해당하면 결과가 달라집니다.")
    return Computation(steps, taxable, calculated, local, "surcharged" if surcharged else "taxed", notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    rows = {key: await get_deduction("양도소득세", name, as_of=as_of) for key, name in DEDUCTION_NAMES.items()}
    basic_row = await get_deduction("소득세", "양도소득기본공제", as_of=as_of)
    brackets = await get_brackets("양도소득세", "기본", as_of=as_of)
    short_rows = {key: await get_brackets("양도소득세", category, as_of=as_of)
                  for key, category in SHORT_RATE_CATEGORIES.items()}
    if not all(short_rows.values()):
        raise CalculationError("missing_tax_data")
    rate = lambda key: Decimal(str(require_value(rows[key], "rate")))
    used = [*rows.values(), basic_row, *brackets, *(r for band in short_rows.values() for r in band)]
    return Parameters(
        brackets=brackets,
        short_rates={key: Decimal(str(require_value(band[0], "rate"))) for key, band in short_rows.items()},
        basic_deduction=int(require_value(basic_row, "amount")),
        high_price_threshold=int(require_value(rows["high_price_threshold"], "amount")),
        general_rate=rate("general_rate"), general_cap=rate("general_cap"),
        home_holding_rate=rate("home_holding_rate"), home_holding_cap=rate("home_holding_cap"),
        home_residence_rate=rate("home_residence_rate"), home_residence_cap=rate("home_residence_cap"),
        surcharges={"2주택": rate("surcharge_two"), "3주택이상": rate("surcharge_three")},
        local_tax_ratio=rate("local_tax_ratio"),
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r and r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r and r.get("source_article")})))


async def calculate(transfer_price: int, acquisition_price: int, expenses: int = 0, holding_years: int = 0,
                    asset_type: str = HOUSE, is_one_home: bool = False, residence_years: int = 0,
                    acquired_in_adjusted_area: bool = False, multi_home_surcharge: str = "없음",
                    as_of: date | None = None) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(params=params, transfer_price=transfer_price, acquisition_price=acquisition_price,
                     expenses=expenses, holding_years=holding_years, asset_type=asset_type,
                     is_one_home=is_one_home, residence_years=residence_years,
                     acquired_in_adjusted_area=acquired_in_adjusted_area, multi_home_surcharge=multi_home_surcharge)
    return CalculationResult(
        tax_type="양도소득세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.calculated_tax,
        effective_rate=round(result.calculated_tax / transfer_price, 6) if transfer_price else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, "최종 납부세액은 양도소득세(국세)이며 지방소득세는 별도로 표시했습니다.", *SCOPE_NOTES])

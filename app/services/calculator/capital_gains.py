"""양도소득세 참고 계산: 부동산(주택·토지·건물)·부동산 권리(분양권·조합원입주권)·기타자산, 주식, 파생상품, 신탁수익권.

소득세법 제89조 제1항 제3호(1세대 1주택 비과세, 고가주택 제외), 제95조(장기보유특별공제 표1·표2),
제103조(양도소득 기본공제), 제104조(세율, 단기보유 세율, 제7항 다주택 중과)와 시행령 제154조
(1세대 1주택 비과세 요건), 제159조의4(표2 적용 1세대 1주택), 제160조(고가주택 양도차익 안분)를 따른다.
산식은 국세청 양도소득세 신고서 작성 사례와 고가주택 계산 안내, 「2026 세금절약가이드 Ⅱ」의
세율 비교표로 검증한다(tests/data/nts_capital_gains.json). 법정 수치는 DB(tax_deductions,
tax_brackets)에서 읽는다.

소득세법 제102조·제103조에 따라 양도소득은 네 그룹(부동산 등, 주식, 파생상품, 신탁수익권)별로 계산하고
그룹마다 기본공제 250만원과 양도차손 통산을 따로 적용한다. 분양권(60%·70%), 조합원입주권(주택 단기세율, 원조합원의
관리처분계획인가 전 양도차익에만 장기보유특별공제), 비사업용 토지(기본세율+10%p), 미등기(70%, 공제 없음),
기타자산(기본세율), 주식(대주주 20·25%·1년 미만 비중소 30%, 소액주주 중소 10%·그 밖 20%, 국외 중소 10%·그 밖 20%,
국내 상장주식 소액주주 장내 양도는 과세 대상 아님), 파생상품(탄력세율 10%), 신탁수익권(20·25%)은 제104조를 따른다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일(양도일)의
수치를 읽어 호출한다. 1세대 1주택 여부·취득 당시 조정대상지역 여부·중과 대상 여부는 사실관계
판단이므로 입력으로 받고, 계산기가 추정하지 않는다.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator import penalty_tax
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

HOUSE, LAND = "주택", "토지·건물"
PRESALE, MEMBERSHIP_RIGHT, OTHER_ASSET = "분양권", "조합원입주권", "기타자산"
STOCK, DERIVATIVE, TRUST = "주식", "파생상품", "신탁수익권"
REAL_ESTATE_GROUP = (HOUSE, LAND, PRESALE, MEMBERSHIP_RIGHT, OTHER_ASSET)
ASSET_TYPES = (*REAL_ESTATE_GROUP, STOCK, DERIVATIVE, TRUST)
STOCK_MARKETS = ("국내상장", "국내비상장", "국외")
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
# 분양권은 보유기간과 상관없이 60%(1년 미만 70%), 그 밖의 그룹 세율도 DB에서 읽는다.
EXTRA_RATE_NAMES = {"presale_short": "분양권_1년미만", "presale": "분양권", "unregistered": "미등기",
                    "non_business_land": "비사업용토지_가산율", "major_short": "주식_대주주_단기_비중소",
                    "minor_sme": "주식_소액_중소", "minor_other": "주식_소액_비중소", "foreign_sme": "주식_국외_중소",
                    "foreign_other": "주식_국외", "derivative": "파생상품_탄력세율"}

SCOPE_NOTES = (
    "거주자의 자산 1건을 그해 같은 그룹의 유일한 양도로 보고 계산했습니다(입력한 같은 그룹 양도차손만 통산). "
    "조세특례제한법 감면, 장기임대주택 특례, 같은 해 여러 건 양도의 비교과세, 조합원입주권 1주택 비과세, 국외 부동산, "
    "외국납부세액공제, 전자신고세액공제는 반영하지 않았습니다.",
    "1세대 1주택·조정대상지역·다주택 중과·비사업용 토지·대주주·중소기업 해당 여부는 입력값을 따른 것이며 계산기가 "
    "사실관계를 판정하지 않습니다.",
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
    extra_rates: dict = None        # EXTRA_RATE_NAMES 키 → 세율
    progressive_major: list = None  # 대주주 주식·신탁수익권 20%·25% 구간
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
    if asset_type not in (HOUSE, MEMBERSHIP_RIGHT) and residence_years:
        raise CalculationError("invalid_input")
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


def _securities(params, *, asset_type, gain, holding_years, stock_market, major_shareholder, sme, steps, notes):
    """주식·파생상품·신탁수익권: 그룹별 기본공제 250만원 뒤 제104조 제1항 제11호~제14호 세율."""
    r = params.extra_rates
    if asset_type == STOCK and stock_market == "국내상장" and not major_shareholder:
        notes.append("국내 상장주식을 대주주가 아닌 사람이 증권시장에서 양도하면 양도소득세 과세 대상이 아닙니다"
                     "(장외에서 양도하면 과세). 증권거래세는 따로 냅니다.")
        steps.append(("과세 대상 아님(상장주식 소액주주 장내 양도)", gain))
        return Computation(steps, 0, 0, 0, "exempt", notes)
    basic = min(gain, params.basic_deduction)
    taxable = gain - basic
    steps += [("양도소득금액", gain), (f"양도소득 기본공제({asset_type} 그룹)", basic), ("과세표준", taxable)]
    if asset_type == DERIVATIVE:
        calculated, label = truncate_won(taxable, r["derivative"]), f"파생상품 탄력세율 {_pct(r['derivative'])}"
    elif asset_type == TRUST or (asset_type == STOCK and stock_market != "국외" and major_shareholder):
        calculated, label = apply_progressive_tax(taxable, params.progressive_major)[0], "20%(3억원 초과분 25%)"
        if asset_type == STOCK and holding_years < 1 and not sme:
            calculated, label = truncate_won(taxable, r["major_short"]), f"대주주 1년 미만 보유 {_pct(r['major_short'])}"
    elif asset_type == STOCK and stock_market == "국외":
        rate = r["foreign_sme" if sme else "foreign_other"]
        calculated, label = truncate_won(taxable, rate), f"국외주식 {'중소기업 ' if sme else ''}{_pct(rate)}"
    else:
        rate = r["minor_sme" if sme else "minor_other"]
        calculated, label = truncate_won(taxable, rate), f"대주주 아닌 {'중소기업 ' if sme else ''}주식 {_pct(rate)}"
    local = truncate_won(calculated, params.local_tax_ratio)
    steps += [(f"산출세액({label})", calculated),
              (f"지방소득세(별도 납부, 산출세액의 {_pct(params.local_tax_ratio)})", local),
              ("양도소득세와 지방소득세 합계", calculated + local)]
    return Computation(steps, taxable, calculated, local, "taxed", notes)


def compute(*, params, transfer_price, acquisition_price, expenses=0, holding_years=0, asset_type=HOUSE,
            is_one_home=False, residence_years=0, acquired_in_adjusted_area=False, multi_home_surcharge="없음",
            non_business_land=False, unregistered=False, pre_approval_gain=0, pre_approval_years=0,
            stock_market="국내비상장", major_shareholder=False, sme=False, same_group_loss=0):
    _check_inputs(asset_type, holding_years, residence_years, is_one_home, multi_home_surcharge)
    if (non_business_land and asset_type != LAND) or (is_one_home and asset_type != HOUSE) or (
            unregistered and asset_type not in REAL_ESTATE_GROUP) or stock_market not in STOCK_MARKETS or (
            pre_approval_gain and asset_type != MEMBERSHIP_RIGHT):
        raise CalculationError("invalid_input")
    gain = transfer_price - acquisition_price - expenses
    steps = [("양도차익(양도가액-취득가액-필요경비)", max(0, gain))]
    notes = []
    if same_group_loss and gain > 0:
        offset = min(gain, same_group_loss)
        gain -= offset
        steps.append(("같은 그룹 다른 자산의 양도차손 통산(제102조 제2항)", offset))
    if asset_type in (STOCK, DERIVATIVE, TRUST) and gain > 0:
        return _securities(params, asset_type=asset_type, gain=gain, holding_years=holding_years,
                           stock_market=stock_market, major_shareholder=major_shareholder, sme=sme,
                           steps=steps, notes=notes)
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
    if unregistered or asset_type in (PRESALE, OTHER_ASSET):
        rate, rate_text = Decimal(0), ("미등기 양도자산은 공제 없음" if unregistered else f"{asset_type}은 공제 대상 아님")
    full_deduction = truncate_won(gain, rate)
    if asset_type == MEMBERSHIP_RIGHT and not unregistered:
        # 제95조 제2항: 원조합원은 관리처분계획인가 전 양도차익에만, 그 전 보유기간으로 공제한다.
        pre_rate, _ = long_term_rate(params, holding_years=pre_approval_years, residence_years=0,
                                     is_one_home=False, surcharged=False)
        full_deduction = truncate_won(min(pre_approval_gain, gain), pre_rate)
        rate_text = (f"관리처분계획인가 전 양도차익 {min(pre_approval_gain, gain):,}원 x {_pct(pre_rate)}"
                     if pre_approval_gain else "승계조합원은 공제 없음")
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
    basic = 0 if unregistered else min(income, params.basic_deduction)
    taxable = income - basic
    steps += [("양도소득금액", income), ("양도소득 기본공제", basic), ("과세표준", taxable)]

    base_tax, base_rate = apply_progressive_tax(taxable, params.brackets)
    r = params.extra_rates or {}
    candidates = [(base_tax, f"기본세율 {base_rate}")]
    if surcharged:
        extra = params.surcharges[multi_home_surcharge]
        candidates = [(base_tax + truncate_won(taxable, extra), f"기본세율 {base_rate} + 중과 {_pct(extra)}p")]
    if non_business_land:
        candidates = [(base_tax + truncate_won(taxable, r["non_business_land"]),
                       f"비사업용 토지 기본세율 {base_rate} + {_pct(r['non_business_land'])}p")]
    if asset_type == PRESALE:
        rate = r["presale_short" if holding_years < 1 else "presale"]
        candidates = [(truncate_won(taxable, rate), f"분양권 {'1년 미만 보유 ' if holding_years < 1 else ''}{_pct(rate)}")]
    elif holding_years < 2 and asset_type in (HOUSE, LAND, MEMBERSHIP_RIGHT):
        short = params.short_rates[(LAND if asset_type == LAND else HOUSE, holding_years)]
        candidates.append((truncate_won(taxable, short),
                           f"{'1년 미만' if holding_years == 0 else '1년 이상 2년 미만'} 보유 {_pct(short)}"))
    if unregistered:
        candidates.append((truncate_won(taxable, r["unregistered"]), f"미등기 양도 {_pct(r['unregistered'])}"))
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
    extra_rows = {}
    for key, name in EXTRA_RATE_NAMES.items():
        try:
            extra_rows[key] = await get_deduction("양도소득세", name, as_of=as_of)
        except CalculationError as exc:
            if exc.code != "missing_tax_data":
                raise
            extra_rows[key] = None   # 그 기준일에 없던 세율은 해당 자산을 계산할 때 멈춘다.
    try:
        major_brackets = await get_brackets("양도소득세", "주식_대주주", as_of=as_of)
    except CalculationError as exc:
        if exc.code != "missing_tax_data":
            raise
        major_brackets = []
    rate = lambda key: Decimal(str(require_value(rows[key], "rate")))
    used = [*rows.values(), basic_row, *brackets, *(r for band in short_rows.values() for r in band),
            *(r for r in extra_rows.values() if r), *major_brackets]
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
        extra_rates={key: Decimal(str(row["rate"])) for key, row in extra_rows.items() if row and row.get("rate") is not None},
        progressive_major=major_brackets,
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r and r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r and r.get("source_article")})))


async def calculate(transfer_price: int, acquisition_price: int, expenses: int = 0, holding_years: int = 0,
                    asset_type: str = HOUSE, is_one_home: bool = False, residence_years: int = 0,
                    acquired_in_adjusted_area: bool = False, multi_home_surcharge: str = "없음",
                    non_business_land: bool = False, unregistered: bool = False, pre_approval_gain: int = 0,
                    pre_approval_years: int = 0, stock_market: str = "국내비상장", major_shareholder: bool = False,
                    sme: bool = False, same_group_loss: int = 0, as_of: date | None = None,
                    **penalty) -> CalculationResult:
    params = await load_parameters(as_of)
    try:
        result = compute(params=params, transfer_price=transfer_price, acquisition_price=acquisition_price,
                         expenses=expenses, holding_years=holding_years, asset_type=asset_type,
                         is_one_home=is_one_home, residence_years=residence_years,
                         acquired_in_adjusted_area=acquired_in_adjusted_area, multi_home_surcharge=multi_home_surcharge,
                         non_business_land=non_business_land, unregistered=unregistered,
                         pre_approval_gain=pre_approval_gain, pre_approval_years=pre_approval_years,
                         stock_market=stock_market, major_shareholder=major_shareholder, sme=sme,
                         same_group_loss=same_group_loss)
    except KeyError as exc:
        raise CalculationError("missing_tax_data") from exc
    summary = CalculationResult(
        tax_type="양도소득세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.calculated_tax,
        effective_rate=round(result.calculated_tax / transfer_price, 6) if transfer_price else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, "최종 납부세액은 양도소득세(국세)이며 지방소득세는 별도로 표시했습니다.", *SCOPE_NOTES])
    return await penalty_tax.attach(summary, result.calculated_tax, as_of=as_of, **penalty)

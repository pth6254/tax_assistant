"""상속세 참고 계산(거주자 사망): 상속재산 → 채무·공과금·장례비용 → 사전증여 가산 → 상속공제(기초·인적·일괄,
배우자, 금융재산)와 공제 한도 → 세율 → 세대생략 할증 → 증여세액공제 → 신고세액공제.

상속세 및 증여세법 제13조(과세가액, 사전증여 가산), 제14조와 시행령 제9조(공과금·장례비용·채무),
제18조~제22조(기초·배우자·그 밖의 인적·일괄·금융재산 공제), 제24조(공제 적용 한도), 제25조(과세표준·
과세최저한), 제26조(세율), 제27조(세대생략 할증), 제28조(증여세액공제), 제69조(신고세액공제)를 따른다.
산식은 국세청 상속세 신고서 작성 사례와 「2026 세금절약가이드 Ⅱ」 사례로 검증한다
(tests/data/nts_inheritance.json). 법정 수치는 DB에서 읽는다.

`compute`는 DB 없이 법정 수치를 받아 계산하는 순수 함수이고, `calculate`가 기준일의 수치를 읽어 호출한다.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.calculator import CalculationResult, TaxBasis, TaxStep
from app.services.calculator.brackets import apply_progressive_tax, truncate_won
from app.services.calculator.errors import CalculationError, require_value
from app.services.calculator.repository import get_brackets, get_deduction

AMOUNTS = {
    "basic": "기초공제", "lump_sum": "일괄공제", "spouse_min": "배우자상속공제_최소", "spouse_max": "배우자상속공제_한도",
    "child": "자녀공제", "minor_year": "미성년자공제_연", "elderly": "연로자공제", "disabled_year": "장애인공제_연",
    "gift_limit_floor": "공제한도_증여가산_기준", "funeral_min": "장례비용_최소", "funeral_max": "장례비용_한도",
    "memorial_max": "봉안비용_한도", "minimum": "과세최저한",
}
FINANCIAL, SURCHARGE, SURCHARGE_LARGE, FILING_CREDIT = "금융재산상속공제", "세대생략할증률", "세대생략할증률_미성년_고액", "신고세액공제율"

SCOPE_NOTES = (
    "상속재산가액은 평가된 금액(간주·추정상속재산 포함)을 입력받으며 재산 평가와 추정상속재산 계산은 하지 "
    "않았습니다. 동거주택·가업·영농 상속공제, 재해손실공제, 감정평가수수료, 외국납부세액공제, 단기재상속 "
    "세액공제, 비거주자 상속과 가산세는 계산하지 않았습니다.",
    "금액은 상속 전체에 대한 참고 계산이며 상속인별 납부세액 배분과 실제 신고세액은 확정하지 않습니다.",
)


@dataclass(frozen=True)
class Parameters:
    brackets: list
    amounts: dict
    financial_rate: Decimal
    financial_min: int
    financial_max: int
    surcharge_rate: Decimal
    surcharge_large_rate: Decimal
    surcharge_large_threshold: int
    filing_credit_rate: Decimal
    effective_dates: tuple = ()
    sources: tuple = ()


@dataclass
class Computation:
    steps: list
    taxable_income: int
    calculated_tax: int
    decided_tax: int
    notes: list


def financial_deduction(params, net_financial):
    """제22조: 2천만원 이하는 전액, 넘으면 20%와 2천만원 중 큰 금액, 2억원 한도."""
    if net_financial <= params.financial_min:
        return max(0, net_financial)
    return min(max(truncate_won(net_financial, params.financial_rate), params.financial_min), params.financial_max)


def spouse_share(children_count, parents_count):
    """민법 제1009조: 배우자는 자녀(없으면 직계존속)의 상속분에 5할을 더한다."""
    others = children_count or parents_count
    return Decimal("1.5") / (Decimal("1.5") + others) if others else Decimal(1)


def compute(*, params, estate_value, debts=0, funeral_expenses=0, memorial_expenses=0, financial_assets=0,
            prior_gifts=0, prior_gifts_non_heirs=0, prior_gifts_taxable=0, prior_gift_tax=0,
            has_spouse=False, spouse_inheritance=0, spouse_prior_gifts_taxable=0, children_count=0,
            parents_count=0, minor_years=0, elderly_count=0, disabled_years=0, non_heir_bequests=0,
            skipped_generation_assets=0, skipped_generation_minor=False, filed_on_time=True):
    a = params.amounts
    has_spouse = has_spouse or spouse_inheritance > 0
    if financial_assets > estate_value or non_heir_bequests > estate_value or skipped_generation_assets > estate_value:
        raise CalculationError("invalid_input")
    notes = []
    funeral = min(max(funeral_expenses, a["funeral_min"]), a["funeral_max"]) + min(memorial_expenses, a["memorial_max"])
    added = prior_gifts + prior_gifts_non_heirs
    base = max(0, estate_value - debts - funeral) + added
    steps = [("상속재산가액(간주·추정상속재산 포함)", estate_value), ("채무·공과금", debts),
             ("장례비용(최소 500만원, 한도 1천만원 + 봉안 500만원)", funeral)]
    if added:
        steps.append(("사전증여재산가액(상속인 10년·그 외 5년 내 증여)", added))
    steps.append(("상속세 과세가액", base))

    # 기초공제+그 밖의 인적공제와 일괄공제 중 큰 금액(배우자 단독상속이면 일괄공제 없음, 제21조).
    personal = (a["child"] * children_count + a["minor_year"] * minor_years + a["elderly"] * elderly_count
                + a["disabled_year"] * disabled_years)
    itemized = a["basic"] + personal
    sole_spouse = has_spouse and not children_count and not parents_count
    basic = itemized if sole_spouse else max(itemized, a["lump_sum"])
    steps.append(("기초공제와 그 밖의 인적공제" if basic == itemized else "일괄공제", basic))

    spouse = 0
    if has_spouse:
        share = spouse_share(children_count, parents_count)
        # 한도 = (상속재산 - 상속인 아닌 수유자 몫 + 상속인 사전증여) x 법정상속분 - 배우자 사전증여 과세표준
        cap_base = estate_value - debts - non_heir_bequests + prior_gifts
        limit = max(0, min(int(Decimal(cap_base) * share) - spouse_prior_gifts_taxable, a["spouse_max"]))
        spouse = max(a["spouse_min"], min(spouse_inheritance, limit))
        steps.append((f"배우자 상속공제(실제 상속 {spouse_inheritance:,}원, 한도 {limit:,}원, 최소 {a['spouse_min']:,}원)", spouse))
        if spouse_inheritance > limit:
            notes.append("배우자가 실제 상속받은 금액이 법정상속분 기준 한도를 넘어 한도까지만 공제했습니다.")
    financial = financial_deduction(params, financial_assets)
    if financial_assets:
        steps.append(("금융재산 상속공제", financial))
    total = basic + spouse + financial
    # 공제 적용 한도(제24조): 상속인 아닌 자의 몫과 가산한 증여재산(과세가액 5억원 초과 시)은 공제받지 못한다.
    excluded = non_heir_bequests + (prior_gifts_taxable if base > a["gift_limit_floor"] else 0)
    limit = max(0, base - excluded)
    applied = min(total, limit)
    steps.append((f"상속공제 합계(공제 적용 한도 {limit:,}원)", applied))
    if total > limit:
        notes.append(f"상속공제 합계 {total:,}원이 공제 적용 한도를 넘어 한도까지만 공제했습니다(제24조).")
    taxable = base - applied
    steps.append(("상속세 과세표준", taxable))
    calculated, rate = apply_progressive_tax(taxable, params.brackets)
    if taxable < a["minimum"]:
        calculated = 0
    steps.append((f"상속세 산출세액(세율 {rate})", calculated))

    surcharge = 0
    if skipped_generation_assets:
        large = skipped_generation_minor and skipped_generation_assets > params.surcharge_large_threshold
        ratio = Decimal(skipped_generation_assets) / (estate_value + added)
        surcharge = truncate_won(calculated, ratio, params.surcharge_large_rate if large else params.surcharge_rate)
        steps.append((f"세대생략 할증과세액({'40' if large else '30'}%, 손자녀 등 몫 비율)", surcharge))
    gift_credit = 0
    if prior_gift_tax:
        cap = int(Decimal(calculated) * prior_gifts_taxable / taxable) if taxable else 0
        gift_credit = min(prior_gift_tax, cap)
        steps.append((f"증여세액공제(사전증여 산출세액 {prior_gift_tax:,}원과 한도 {cap:,}원 중 작은 금액)", gift_credit))
    filing = truncate_won(calculated + surcharge - gift_credit, params.filing_credit_rate) if filed_on_time else 0
    steps.append(("신고세액공제(3%)" if filed_on_time else "신고세액공제(기한 내 신고 아님)", filing))
    decided = max(0, calculated + surcharge - gift_credit - filing)
    steps.append(("납부할 세액", decided))
    if prior_gifts and not prior_gift_tax:
        notes.append("가산한 사전증여재산에 대해 낸 증여세(산출세액)를 입력하지 않아 증여세액공제를 하지 않았습니다.")
    if filed_on_time:
        notes.append("상속개시일이 속하는 달의 말일부터 6개월 안에 신고하는 것으로 보아 신고세액공제 3%를 적용했습니다.")
    return Computation(steps, taxable, calculated, decided, notes)


async def load_parameters(as_of: date | None = None) -> Parameters:
    names = [*AMOUNTS.values(), FINANCIAL, SURCHARGE, SURCHARGE_LARGE, FILING_CREDIT]
    rows = {name: await get_deduction("상속세", name, as_of=as_of) for name in names}
    brackets = await get_brackets("상속세", "default", as_of=as_of)
    used = [r for r in [*rows.values(), *brackets] if r]
    return Parameters(
        brackets=brackets, amounts={key: int(require_value(rows[name], "amount")) for key, name in AMOUNTS.items()},
        financial_rate=Decimal(str(require_value(rows[FINANCIAL], "rate"))),
        financial_min=int(require_value(rows[FINANCIAL], "amount")),
        financial_max=int(require_value(rows[FINANCIAL], "max_amount")),
        surcharge_rate=Decimal(str(require_value(rows[SURCHARGE], "rate"))),
        surcharge_large_rate=Decimal(str(require_value(rows[SURCHARGE_LARGE], "rate"))),
        surcharge_large_threshold=int(require_value(rows[SURCHARGE_LARGE], "amount")),
        filing_credit_rate=Decimal(str(require_value(rows[FILING_CREDIT], "rate"))),
        effective_dates=tuple(sorted({str(r["effective_date"]) for r in used if r.get("effective_date")})),
        sources=tuple(sorted({r["source_article"] for r in used if r.get("source_article")})))


async def calculate(estate_value: int, debts: int = 0, spouse_inheritance: int = 0, children_count: int = 0,
                    funeral_expenses: int = 0, memorial_expenses: int = 0, financial_assets: int = 0,
                    prior_gifts: int = 0, prior_gifts_non_heirs: int = 0, prior_gifts_taxable: int = 0,
                    prior_gift_tax: int = 0, has_spouse: bool = False, spouse_prior_gifts_taxable: int = 0,
                    parents_count: int = 0, minor_years: int = 0, elderly_count: int = 0, disabled_years: int = 0,
                    non_heir_bequests: int = 0, skipped_generation_assets: int = 0,
                    skipped_generation_minor: bool = False, filed_on_time: bool = True,
                    as_of: date | None = None) -> CalculationResult:
    params = await load_parameters(as_of)
    result = compute(
        params=params, estate_value=estate_value, debts=debts, funeral_expenses=funeral_expenses,
        memorial_expenses=memorial_expenses, financial_assets=financial_assets, prior_gifts=prior_gifts,
        prior_gifts_non_heirs=prior_gifts_non_heirs, prior_gifts_taxable=prior_gifts_taxable,
        prior_gift_tax=prior_gift_tax, has_spouse=has_spouse, spouse_inheritance=spouse_inheritance,
        spouse_prior_gifts_taxable=spouse_prior_gifts_taxable, children_count=children_count,
        parents_count=parents_count, minor_years=minor_years, elderly_count=elderly_count,
        disabled_years=disabled_years, non_heir_bequests=non_heir_bequests,
        skipped_generation_assets=skipped_generation_assets, skipped_generation_minor=skipped_generation_minor,
        filed_on_time=filed_on_time)
    return CalculationResult(
        tax_type="상속세",
        steps=[TaxStep(label=label, amount=amount) for label, amount in result.steps],
        taxable_income=result.taxable_income, calculated_tax=result.calculated_tax, final_tax=result.decided_tax,
        effective_rate=round(result.decided_tax / estate_value, 6) if estate_value else 0.0,
        source_articles=list(params.sources),
        basis=TaxBasis(queried_on=(as_of or date.today()).isoformat(), effective_dates=list(params.effective_dates)),
        notes=[*result.notes, *SCOPE_NOTES])

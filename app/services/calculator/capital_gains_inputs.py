"""Read a real-estate capital gains question into calculator inputs plus stated assumptions.

Amounts, periods and the kind of property must be written by the user. Facts that decide
whether the sale is exempt (1세대 1주택, 거주기간, 취득 당시 조정대상지역) are never assumed: when
one is missing the reader names it so the chat can ask. Only the necessary expenses
default to zero, and that assumption is shown with the result. Anything the calculator
does not model (다주택 중과 판단, 분양권, 비사업용 토지, 주식 …) returns None so the question takes the
ordinary tool path.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import _MONEY, _PARTICLE, parse_money, stated_amount

TRANSFER_LABEL = r"양도가액|양도가|양도 가액|양도금액|매도가액|매도가|매도 금액|매매가|판매가"
ACQUISITION_LABEL = r"취득가액|취득가|취득 가액|취득금액|매수가|매입가|구입가|분양가"
EXPENSE_LABEL = r"필요경비|경비"
SELL_VERB = r"(?:에|으로|로)\s*(?:팔|매도|양도|처분|판매)"
BUY_VERB = r"(?:에|으로|로)\s*(?:샀|사서|산(?=\s|$|[,.])|사고|구입|구매|매수|매입|취득|분양)"
HOUSE = re.compile(r"아파트|주택|빌라|다세대|연립|단독|(?<![가-힣])집(?![합중계값])")
LAND = re.compile(r"토지|땅|임야|상가|건물|공장|창고|나대지")
UNSUPPORTED = re.compile(
    r"오피스텔|분양권|입주권|주식|코인|가상자산|채권|펀드|파생|비사업용|농지|자경|미등기|비거주자|해외|국외|"
    r"상속받은|증여받은|감면|임대사업|장기임대|겸용|부수토지|일시적")
MULTI_HOME = re.compile(r"다주택|(?<!\d)[2-9]\s*주택|두\s*채|세\s*채|[2-9]\s*채|중과")
ONE_HOME = re.compile(r"1\s*세대\s*1\s*주택|(?<![\d가-힣])1\s*주택|일주택|(?:집|주택|아파트)\s*(?:한|1)\s*채|한\s*채(?:만|뿐)?")
NOT_LIVED = re.compile(r"(?:거주|실거주|살)(?:하지|지|은|는)?\s*(?:않|안\s*(?:했|함|하))|거주\s*(?:안|없)|전세\s*(?:주|줬|놓)|임대\s*(?:줬|주고|놓)")
LIVED_THROUGHOUT = re.compile(r"(?:계속|쭉|내내|줄곧|보유\s*기간\s*(?:동안|내내))\s*(?:거주|살)")
ADJUSTED = re.compile(r"조정\s*대상\s*지역|조정\s*지역")
NOT_ADJUSTED = re.compile(r"비\s*조정|조정\s*(?:대상\s*)?지역(?:이|은|에)?\s*(?:아니|아닌|아닙|해제)")
YEARS = r"(\d+)\s*년"


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def _verb_amount(verb, text):
    values = {parse_money(m.group(1)) for m in re.finditer(r"(" + _MONEY.pattern + r")\s*" + verb, text)}
    if len(values) > 1:
        raise ValueError("conflicting_amounts")
    return values.pop() if values else None


def _amount(label, verb, texts):
    """The latest turn that states the amount wins; a turn stating it twice differently is ambiguous."""
    for text in reversed(texts):
        labelled = stated_amount(label, text)
        spoken = _verb_amount(verb, text) if verb else None
        if labelled is not None and spoken is not None and labelled != spoken:
            raise ValueError("conflicting_amounts")
        if labelled is not None or spoken is not None:
            return labelled if labelled is not None else spoken
    return None


def _holding_years(text):
    patterns = [r"보유\s*기간\s*(?:은|는|이|:)?\s*" + YEARS,
                YEARS + r"\s*(?:\d+\s*개월\s*)?(?:동안\s*|간\s*)?(?:보유|가지고|갖고|소유)",
                YEARS + r"\s*전에?\s*(?:샀|사서|산|구입|구매|취득|매수|분양)"]
    months = [r"(\d+)\s*개월\s*(?:동안\s*|간\s*)?(?:보유|가지고|갖고|소유)", r"(\d+)\s*개월\s*전에?\s*(?:샀|사서|산|구입|취득|매수)"]
    values = {int(m.group(1)) for p in patterns for m in re.finditer(p, text)}
    values |= {int(m.group(1)) // 12 for p in months for m in re.finditer(p, text)
               if not re.search(r"\d\s*년\s*$", text[:m.start()])}
    if len(values) > 1:
        raise ValueError("conflicting_periods")
    return values.pop() if values else None


def _residence_years(text, holding):
    if NOT_LIVED.search(text):
        return 0
    if LIVED_THROUGHOUT.search(text) and holding is not None:
        return holding
    patterns = [r"거주\s*기간\s*(?:은|는|이|:)?\s*" + YEARS,
                YEARS + r"\s*(?:\d+\s*개월\s*)?(?:동안\s*|간\s*)?(?:거주|실거주|살았|살고|살다)"]
    values = {int(m.group(1)) for p in patterns for m in re.finditer(p, text)}
    if len(values) > 1:
        raise ValueError("conflicting_periods")
    return values.pop() if values else None


def stated_capital_gains_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text) or MULTI_HOME.search(text):
        return None
    try:
        transfer = _amount(TRANSFER_LABEL, SELL_VERB, texts)
        acquisition = _amount(ACQUISITION_LABEL, BUY_VERB, texts)
        expenses = _amount(EXPENSE_LABEL, None, texts)
        holding = next((h for h in (_holding_years(t) for t in reversed(texts)) if h is not None), None)
        residence = next((r for r in (_residence_years(t, holding) for t in reversed(texts)) if r is not None), None)
    except ValueError:
        return None
    if transfer is None:
        return None   # Not recognisably a sale with a price: leave it to the ordinary path.
    house, land = bool(HOUSE.search(text)), bool(LAND.search(text))
    if house and land:
        return None
    missing = []
    if acquisition is None:
        missing.append("취득가액")
    if holding is None:
        missing.append("보유기간")
    if not (house or land):
        missing.append("양도한 자산 종류(주택 또는 토지·건물)")
    one_home = bool(ONE_HOME.search(text))
    if house and not one_home:
        missing.append("1세대 1주택 여부(양도일 현재 세대가 가진 주택 수)")
    if house and one_home and (holding is None or holding >= 2):
        if residence is None:
            missing.append("보유기간 중 거주기간")
        elif residence < 2 and not (ADJUSTED.search(text) or NOT_ADJUSTED.search(text)):
            missing.append("취득 당시 조정대상지역이었는지")
    if missing:
        return MissingInputs(missing)
    if residence is not None and residence > holding:
        return None
    assumptions = []
    if expenses is None:
        expenses = 0
        assumptions.append("필요경비(취득세·중개수수료·자본적지출 등)는 0원으로 계산했습니다. 증빙이 있는 필요경비를 알려주시면 세금이 줄어듭니다.")
    if land:
        assumptions.append("비사업용 토지가 아니고 등기된 국내 자산으로 보았습니다(비사업용 토지는 세율이 10%p 높습니다).")
    else:
        assumptions.append("등기된 국내 주택을 거주자가 양도하는 것으로 보았습니다.")
    assumptions.append(f"보유기간은 만 {holding}년"
                       + (f", 거주기간은 만 {residence}년" if house and residence is not None else "")
                       + "으로 계산했습니다(1년 미만 기간은 버림).")
    params = {
        "transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses,
        "holding_years": holding, "asset_type": "주택" if house else "토지·건물",
        "is_one_home": house and one_home, "residence_years": residence if house and residence is not None else 0,
        "acquired_in_adjusted_area": bool(ADJUSTED.search(text)) and not NOT_ADJUSTED.search(text),
        "multi_home_surcharge": "없음",
    }
    return StatedInputs(params, assumptions)

"""Read a real-estate capital gains question into calculator inputs plus stated assumptions.

Amounts, periods and the kind of property must be written by the user. Facts that decide
whether the sale is exempt (1세대 1주택, 거주기간, 취득 당시 조정대상지역) are never assumed: when
one is missing the reader names it so the chat can ask. Only the necessary expenses
default to zero, and that assumption is shown with the result. Anything the calculator
does not model returns None so the question takes the ordinary tool path.

Besides houses and land it reads 분양권, 조합원입주권, 기타자산(회원권), 비사업용 토지, 미등기, 주식(상장·비상장·국외),
파생상품. Facts that set the rate are asked: whether a stockholder is a 대주주, whether a 다주택 house is in a
조정대상지역 and, if so, whether it is subject to the surcharge (exclusions are too many to judge here).
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
    r"오피스텔|코인|가상자산|비트코인|채권|펀드|농지|자경|비거주자|해외\s*부동산|국외\s*부동산|해외\s*(?:아파트|주택|토지)|"
    r"상속받은|증여받은|감면|임대사업|장기임대|겸용|부수토지|일시적|ETF|ELS|리츠")
MULTI_HOME = re.compile(r"다주택|(?<!\d)[2-9]\s*주택|두\s*채|세\s*채|[2-9]\s*채")
THREE_PLUS = re.compile(r"(?<!\d)[3-9]\s*주택|세\s*채|[3-9]\s*채|3주택\s*이상")
SURCHARGE_YES = re.compile(r"중과\s*(?:대상|적용|된다|돼|받)")
SURCHARGE_NO = re.compile(r"중과\s*(?:배제|제외|대상\s*(?:이\s*)?아니|안\s*(?:돼|되|받))")
PRESALE = re.compile(r"분양권")
MEMBERSHIP_RIGHT = re.compile(r"입주권|조합원\s*입주")
ORIGINAL_MEMBER = re.compile(r"원조합원|기존\s*(?:주택|집)(?:을|를)?\s*(?:갖고|가지고|보유)")
PRE_APPROVAL = r"관리처분\s*(?:계획)?\s*인가\s*전\s*(?:양도)?차익|인가\s*전\s*차익"
OTHER_ASSET = re.compile(r"회원권|골프|콘도|헬스|영업권|이축권")
NON_BUSINESS = re.compile(r"비사업용")
UNREGISTERED = re.compile(r"미등기")
STOCK = re.compile(r"주식|지분|상장사|비상장")
FOREIGN_STOCK = re.compile(r"해외\s*주식|미국\s*주식|국외\s*주식|나스닥|뉴욕\s*증시|해외\s*상장|외국\s*주식")
UNLISTED = re.compile(r"비상장|장외")
LISTED = re.compile(r"(?<!비)상장|코스피|코스닥|증시")
MAJOR = re.compile(r"대주주")
NOT_MAJOR = re.compile(r"대주주\s*(?:가|는|이)?\s*아니|소액\s*주주|개미")
SME = re.compile(r"중소기업|중소\s*기업")
DERIVATIVE = re.compile(r"파생|선물|옵션|CFD", re.I)
LOSS = r"손실|양도차손"
# "1세대 1주택이 아니야" names the rule only to deny it.
NOT_ONE_HOME = re.compile(r"(?:1\s*세대\s*)?1\s*주택(?:자)?\s*(?:이|은|는|가|에)?\s*(?:아니|아닌|아닙|해당\s*(?:안|하지\s*않|되지\s*않|없))|"
                          r"1\s*세대\s*1\s*주택(?:이|은|는)?\s*(?:안\s*돼|못)")
# 같은 해 먼저 양도한 자산이 있으면 기본공제는 이미 쓰였고 제104조 제5항의 비교과세를 한다.
PRIOR_SALE = re.compile(r"(?:이미|먼저|앞서)[^.\n]{0,20}?(?:팔았|팔고|양도했|양도하고|양도한|매도했|매도하고|처분했)|"
                        r"같은\s*해[^.\n]{0,20}?(?:팔|양도|매도)|올해\s*(?:두|2|세|3)\s*(?:번째|건)")
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
    patterns = [r"보유\s*(?:기간\s*)?(?:은|는|이|:)?\s*" + YEARS,
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
    patterns = [r"(?<!비)거주\s*(?:기간\s*)?(?:은|는|이|:)?\s*" + YEARS,
                YEARS + r"\s*(?:\d+\s*개월\s*)?(?:동안\s*|간\s*)?(?:거주|실거주|살았|살고|살다)"]
    values = {int(m.group(1)) for p in patterns for m in re.finditer(p, text)}
    if len(values) > 1:
        raise ValueError("conflicting_periods")
    return values.pop() if values else None


def _securities(text, transfer, acquisition, expenses, holding):
    """주식·파생상품: 대주주 여부와 상장 구분이 세율을 정한다."""
    if DERIVATIVE.search(text):
        return StatedInputs({"transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses or 0,
                             "holding_years": holding or 0, "asset_type": "파생상품"},
                            ["파생상품 양도차익에 기본공제 250만원 뒤 탄력세율 10%를 적용했습니다(같은 해 다른 파생상품 손익은 없다고 봄)."])
    market = "국외" if FOREIGN_STOCK.search(text) else "국내비상장" if UNLISTED.search(text) else (
        "국내상장" if LISTED.search(text) else None)
    major = False if NOT_MAJOR.search(text) else True if MAJOR.search(text) else None
    missing = []
    if market is None:
        missing.append("주식이 국내 상장주식인지, 비상장주식인지, 해외주식인지")
    if market in ("국내상장", "국내비상장") and major is None:
        missing.append("대주주인지(상장 지분 1%·코스닥 2% 또는 시가 50억원 이상, 비상장 4% 또는 10억원 이상 등)")
    if market and market != "국외" and major and holding is None and not SME.search(text):
        missing.append("주식 보유기간(대주주가 1년 안에 팔면 30%)")
    if missing:
        return MissingInputs(missing)
    sme = bool(SME.search(text))
    assumptions = [f"{market} 주식 1건을 그해 유일한 주식 양도로 보았습니다(같은 해 다른 주식·해외주식 손익과 통산 안 함).",
                   "증권거래세 등 필요경비는 말씀하신 금액만 뺐습니다." if expenses else "증권거래세 등 필요경비는 0원으로 보았습니다."]
    if market != "국외" and not sme and not (market == "국내상장" and not major):
        assumptions.append("중소기업 주식이 아닌 것으로 보았습니다(중소기업이면 세율이 낮아집니다).")
    if market == "국외":
        assumptions.append("국외주식은 국내 중소기업 주식이 아니므로 20% 세율을 적용했습니다.")
    return StatedInputs({"transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses or 0,
                         "holding_years": holding if holding is not None else 3, "asset_type": "주식",
                         "stock_market": market, "major_shareholder": bool(major), "sme": sme}, assumptions)


def stated_capital_gains_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
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
    if STOCK.search(text) or DERIVATIVE.search(text):
        if acquisition is None:
            return MissingInputs(["취득가액(산 금액)"])
        return _securities(text, transfer, acquisition, expenses, holding)
    prior = _prior_sale(texts)
    result = _real_estate(text, transfer, acquisition, expenses, holding, residence)
    if prior is None or result is None:
        return result
    if hasattr(prior, "labels") or hasattr(result, "labels"):
        return MissingInputs([*getattr(result, "labels", []), *getattr(prior, "labels", [])])
    result.params.update(prior)
    result.assumptions.append(f"같은 해 먼저 양도한 자산(과세표준 {prior['prior_same_year_taxable']:,}원, 산출세액 "
                              f"{prior['prior_same_year_tax']:,}원)과 합산 비교과세했고, 기본공제는 먼저 양도한 자산에서 받은 것으로 "
                              "보았습니다(제104조 제5항).")
    return result


def _prior_sale(texts):
    """None (no earlier sale this year), the earlier sale's figures, or MissingInputs asking for them."""
    text = "\n".join(texts)
    if not PRIOR_SALE.search(text):
        return None
    try:
        taxable = next((v for v in (stated_amount(r"과세표준", t) for t in reversed(texts)) if v is not None), None)
        tax = next((v for v in (stated_amount(r"산출세액", t) for t in reversed(texts)) if v is not None), None)
    except ValueError:
        return MissingInputs(["같은 해 먼저 양도한 자산의 양도소득 과세표준과 산출세액"])
    if taxable is None or tax is None:
        return MissingInputs(["같은 해 먼저 양도한 부동산 등의 양도소득 과세표준과 산출세액(합산 비교과세에 쓰고, "
                              "기본공제 250만원은 먼저 양도한 자산에서 받은 것으로 봄)"])
    return {"prior_same_year_taxable": taxable, "prior_same_year_tax": tax}


def _real_estate(text, transfer, acquisition, expenses, holding, residence):
    """부동산·권리: 주택, 토지·건물, 분양권, 조합원입주권, 기타자산."""
    special = ("분양권" if PRESALE.search(text) else "조합원입주권" if MEMBERSHIP_RIGHT.search(text)
               else "기타자산" if OTHER_ASSET.search(text) else None)
    if special:
        return _rights(text, special, transfer, acquisition, expenses, holding)
    house, land = bool(HOUSE.search(text)), bool(LAND.search(text))
    if house and land:
        return None
    if house and (MULTI_HOME.search(text) or NOT_ONE_HOME.search(text)):
        return _multi_home(text, transfer, acquisition, expenses, holding)
    missing = []
    if acquisition is None:
        missing.append("취득가액")
    if holding is None:
        missing.append("보유기간")
    if not (house or land):
        missing.append("양도한 자산 종류(주택 또는 토지·건물)")
    one_home = bool(ONE_HOME.search(text)) and not NOT_ONE_HOME.search(text)
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
    if land and NON_BUSINESS.search(text):
        assumptions.append("비사업용 토지로 보아 기본세율에 10%p를 더했습니다(장기보유특별공제는 적용).")
    if UNREGISTERED.search(text):
        assumptions.append("미등기 양도자산으로 보아 70% 세율을 적용하고 장기보유특별공제·기본공제를 하지 않았습니다.")
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
        "multi_home_surcharge": "없음", "non_business_land": land and bool(NON_BUSINESS.search(text)),
        "unregistered": bool(UNREGISTERED.search(text)),
    }
    return StatedInputs(params, assumptions)


def _rights(text, asset, transfer, acquisition, expenses, holding):
    """분양권·조합원입주권·기타자산(회원권 등)."""
    missing = []
    if acquisition is None:
        missing.append("취득가액")
    if holding is None and asset != "기타자산":
        missing.append("보유기간(1년 미만·2년 미만이면 세율이 달라짐)")
    pre_gain = None
    if asset == "조합원입주권" and ORIGINAL_MEMBER.search(text):
        try:
            pre_gain = _amount(PRE_APPROVAL, None, [text])
        except ValueError:
            return None
        if pre_gain is None:
            missing.append("관리처분계획인가 전 양도차익(원조합원은 이 부분에만 장기보유특별공제)과 인가 전 보유기간")
    if missing:
        return MissingInputs(missing)
    params = {"transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses or 0,
              "holding_years": holding or 0, "asset_type": asset, "unregistered": bool(UNREGISTERED.search(text))}
    assumptions = ["필요경비는 말씀하신 금액만 뺐습니다." if expenses else "필요경비(취득세·중개수수료 등)는 0원으로 보았습니다."]
    if asset == "분양권":
        assumptions.append("주택분양권으로 보아 60%(1년 미만 70%) 세율을 적용했고 장기보유특별공제는 없습니다.")
    elif asset == "조합원입주권":
        if pre_gain is not None:
            years = re.search(r"인가\s*전[^\d]{0,10}(\d+)\s*년", text)
            params.update(pre_approval_gain=pre_gain, pre_approval_years=int(years.group(1)) if years else holding or 0)
            assumptions.append("원조합원으로 보아 관리처분계획인가 전 양도차익에만 장기보유특별공제를 적용했습니다.")
        else:
            assumptions.append("승계조합원(입주권을 사서 보유)으로 보아 장기보유특별공제를 적용하지 않았습니다. 원조합원이면 "
                               "인가 전 양도차익을 알려주세요.")
        assumptions.append("조합원입주권 1주택 비과세 특례는 판단하지 않았습니다.")
    else:
        assumptions.append("회원권 등 기타자산으로 보아 보유기간과 상관없이 기본세율을 적용했고 장기보유특별공제는 없습니다.")
    return StatedInputs(params, assumptions)


def _multi_home(text, transfer, acquisition, expenses, holding):
    """다주택: 조정대상지역이 아니면 일반과세, 조정대상지역이면 중과 대상인지 사실을 묻는다."""
    adjusted = False if NOT_ADJUSTED.search(text) else True if ADJUSTED.search(text) else None
    missing = []
    if acquisition is None:
        missing.append("취득가액")
    if holding is None:
        missing.append("보유기간")
    if adjusted is None:
        missing.append("양도하는 주택이 양도일 현재 조정대상지역에 있는지")
    elif adjusted and not (SURCHARGE_YES.search(text) or SURCHARGE_NO.search(text)):
        missing.append("다주택 중과 대상인지(일시적 2주택·장기임대주택·상속주택 등 중과 배제 주택이면 아님)")
    if missing:
        return MissingInputs(missing)
    surcharge = "없음"
    if adjusted and SURCHARGE_YES.search(text) and not SURCHARGE_NO.search(text):
        surcharge = "3주택이상" if THREE_PLUS.search(text) else "2주택"
    params = {"transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses or 0,
              "holding_years": holding, "asset_type": "주택", "is_one_home": False, "residence_years": 0,
              "acquired_in_adjusted_area": False, "multi_home_surcharge": surcharge}
    assumptions = ["필요경비는 말씀하신 금액만 뺐습니다." if expenses else "필요경비(취득세·중개수수료 등)는 0원으로 보았습니다.",
                   "다주택자의 주택이라 1세대 1주택 비과세·표2 공제 없이 계산했습니다."]
    assumptions.append(f"조정대상지역 다주택 중과({surcharge})를 적용해 장기보유특별공제를 빼지 않았습니다. 중과 한시 배제는 "
                       "2026-05-09 양도분까지였습니다." if surcharge != "없음" else
                       "중과 대상이 아니라고 보아 기본세율과 장기보유특별공제(표1)를 적용했습니다.")
    return StatedInputs(params, assumptions)

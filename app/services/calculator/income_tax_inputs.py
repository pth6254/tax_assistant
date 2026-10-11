"""Read a comprehensive income tax question into calculator inputs plus stated assumptions.

The kind of each income decides its deduction and credit, so it must be named: 총급여(연봉),
사업 수입금액과 필요경비 (or 사업소득금액), 기타·연금소득금액, and 이자·배당 금융소득. A bare
"소득 5천만원", business revenue without its expenses, or a 기타·연금소득 given before its own
deduction is asked back (MissingInputs) instead of guessed. What only lowers the tax when the user
has it (부양가족, 그 밖의 소득공제·세액공제, 이미 낸 세금) defaults to none, and each such default
is listed with the result. Anything the calculator does not model returns None.

Pensions are split into 공적연금 (국민연금 등) and 사적연금 (연금저축·IRP); lecture and manuscript fees use the
60% deemed expense; house rental, estimated business income (단순·기준경비율 given as rates) and daily
wages are read too. Where the law lets the taxpayer choose separate taxation, the calculator compares both.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import (_MONEY, UNSUPPORTED as FINANCIAL_UNSUPPORTED,
                                                      ambiguous_thousands, parse_money, stated_amount,
                                                      stated_financial_amounts, withholding_stated)

WAGE = r"총급여액|총급여|연봉|급여"
REVENUE = r"사업\s*수입금액|총수입금액|수입금액|사업\s*수입|매출액|매출|수입|사업소득(?!\s*금액)"
EXPENSE = r"필요경비|경비|비용"
BUSINESS_AMOUNT = r"사업소득금액|사업\s*소득금액"
OTHER_AMOUNT = r"기타소득금액|연금소득금액|다른 종합소득금액|다른 종합소득|다른 소득금액|다른 소득|그 밖의 소득금액"
GROSS_ONLY = {"기타소득": r"기타소득(?!\s*금액)", "연금소득": r"연금소득(?!\s*금액)"}
WAGE_AMOUNT = r"근로소득금액"
DEDUCTIONS = r"종합소득공제|소득공제"
CREDITS = r"그 밖의 세액공제|세액공제"
PREPAID = r"기납부세액|기납부 세액|이미 낸 세금|중간예납세액|중간예납"
BARE_INCOME = re.compile(r"(?<![가-힣])(?:소득|돈)(?:\s|은|는|이|가|으로|로|만|이고)*\d")
COUNT = re.compile(r"(?:기본공제|공제)\s*(?:대상)?\s*(?:인원)?\s*(?:은|는|이|가|:)?\s*(\d+)\s*명")
DEPENDANTS = re.compile(r"부양가족(?:은|는|이|가|:)?\s*(\d+)\s*명")
UNSUPPORTED = re.compile(
    FINANCIAL_UNSUPPORTED.pattern + r"|퇴직금|퇴직소득|양도|증여|상속|법인세|법인소득|월급|월\s*급여|"
    r"공동사업|감면|가산세|의료비|교육비|보험료|기부금|자녀세액|연금계좌\s*세액|신용카드|중소기업|매월|월\s*소득|"
    r"복권|당첨|로또|상가\s*임대|사무실\s*임대|점포")
PUBLIC_PENSION = r"국민연금|공무원연금|군인연금|사학연금|공적연금"
PRIVATE_PENSION = r"연금저축|IRP|개인형\s*퇴직연금|퇴직연금|사적연금|개인연금"
DEEMED_60 = r"강연료|강의료|원고료|인세|자문료|심사료|출연료|번역료"
RENTAL = r"주택\s*임대\s*(?:수입금액|수입|소득)|주택임대료|월세\s*(?:수입|소득)|임대료\s*수입"
RENTAL_EXPENSE = r"임대\s*(?:필요경비|경비|비용)"
REGISTERED = re.compile(r"등록\s*임대|임대사업자\s*등록|등록한\s*임대|등록된\s*임대")
RATE = r"\s*(?:은|는|이|:)?\s*(\d+(?:\.\d+)?)\s*%"
SIMPLE_RATE, EXCESS_RATE, STANDARD_RATE = (re.compile(r"단순경비율" + RATE), re.compile(r"초과율" + RATE),
                                           re.compile(r"기준경비율" + RATE))
MAJOR = r"주요경비"
DAILY_WAGE = r"일당|일급"
DAYS = re.compile(r"(\d+)\s*일\s*(?:동안|간|일했|일하|근무|일을)")
AGE = re.compile(r"(?<!\d)(\d{2})\s*(?:세|살)")
DEPOSIT = r"(?:임대\s*)?보증금(?:\s*합계|\s*총액)?|전세\s*보증금"
DEPOSIT_WORDS = re.compile(r"보증금|간주임대료|전세")
HOUSE_COUNT = re.compile(r"(?<!\d)(\d+)\s*(?:채|주택(?!\s*임대)|가구)|(한|두|세|네|다섯)\s*채")
KOREAN_COUNT = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
RELIGIOUS = r"종교인\s*소득|종교인"
RELIGIOUS_AS_WAGE = re.compile(r"근로소득으로\s*(?:신고|원천징수|받|처리)")
SINCERE = re.compile(r"(?<![가-힣])성실사업자(?!\s*(?:가|는|이)?\s*아니)")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def _latest(label, texts):
    """The latest turn stating the amount wins; a turn stating it twice differently is unclear."""
    for text in reversed(texts):
        value = stated_amount(label, text)
        if value is not None:
            return value
    return None


def _count(texts):
    for text in reversed(texts):
        if m := COUNT.search(text):
            return int(m.group(1)), None
        if m := DEPENDANTS.search(text):
            return int(m.group(1)) + 1, f"부양가족 {m.group(1)}명에 본인을 더해 기본공제 {int(m.group(1)) + 1}명으로 계산했습니다."
    return None, None


def _near(label, texts):
    """An amount written within a few words after a label ('국민연금 연금소득 1,200만원')."""
    pattern = re.compile(r"(?:" + label + r")[^\d\n,.]{0,12}?(" + _MONEY.pattern + r")")
    for text in reversed(texts):
        values = {parse_money(m.group(1)) for m in pattern.finditer(text)}
        if len(values) > 1:
            raise ValueError("conflicting_amounts")
        if values:
            return values.pop()
    return None


def _rate_of(pattern, text):
    m = pattern.search(text)
    return float(m.group(1)) if m else None


def stated_income_tax_inputs(query, history=None, *, basic_deduction):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    try:
        wage = _latest(WAGE, texts)
        revenue, expense = _latest(REVENUE, texts), _latest(EXPENSE, texts)
        business_amount = _latest(BUSINESS_AMOUNT, texts)
        other = _latest(OTHER_AMOUNT, texts)
        gross_only = {name: _latest(label, texts) for name, label in GROSS_ONLY.items()}
        wage_amount = _latest(WAGE_AMOUNT, texts)
        deductions, credits, prepaid = _latest(DEDUCTIONS, texts), _latest(CREDITS, texts), _latest(PREPAID, texts)
        public_pension, private_pension = _near(PUBLIC_PENSION, texts), _near(PRIVATE_PENSION, texts)
        fee = _near(DEEMED_60, texts)
        rental, rental_expense = _near(RENTAL, texts), _near(RENTAL_EXPENSE, texts)
        major, daily = _latest(MAJOR, texts), _near(DAILY_WAGE, texts)
        deposits, religious = _near(DEPOSIT, texts), _near(RELIGIOUS, texts)
    except ValueError:
        return None
    if DEPOSIT_WORDS.search(text) and deposits is None:
        return None   # 보증금이 말해졌지만 금액을 읽지 못함: 추측하지 않는다.
    if re.search(r"종교인", text) and religious is None:
        return None
    houses = None
    if deposits is not None and (m := HOUSE_COUNT.search(text)):
        houses = int(m.group(1)) if m.group(1) else KOREAN_COUNT[m.group(2)]
    simple_rate, excess_rate = _rate_of(SIMPLE_RATE, text), _rate_of(EXCESS_RATE, text)
    standard_rate = _rate_of(STANDARD_RATE, text)
    method = "기준경비율" if re.search(r"기준경비율", text) else "단순경비율" if re.search(r"단순경비율", text) else "장부"
    days = int(m.group(1)) if (m := DAYS.search(text)) else None
    age = int(m.group(1)) if (m := AGE.search(text)) else None
    if rental is not None and revenue == rental:
        revenue = None   # "주택임대 수입 1,200만원" is the rental, not business revenue
    if fee is not None:
        gross_only["기타소득"] = None
    if public_pension is not None or private_pension is not None:
        gross_only["연금소득"] = None
    # Financial amounts are read as a group from the latest turn that states one, so a
    # follow-up "이자 1억 5천이면?" replaces the earlier "금융소득 1억" instead of adding to it.
    financial, financial_assumptions = {}, []
    for turn in reversed(texts):
        found = stated_financial_amounts(turn)
        if found is None:
            return None
        if found[0]:
            financial, financial_assumptions = found
            break
    if business_amount is not None and revenue is not None:
        return None   # 소득금액 and 수입금액 together: which one is meant is not certain
    if prepaid is not None and financial and re.search(r"원천징수세액", text):
        return None
    stated_kinds = [wage, revenue, business_amount, other, *gross_only.values(), wage_amount, public_pension,
                    private_pension, fee, rental, daily, deposits, religious]
    if not financial and all(v is None for v in stated_kinds):
        # A bare "소득 5천만원" does not say which deduction and credit apply.
        return MissingInputs(["소득의 종류(근로소득 총급여액, 사업소득 수입금액과 필요경비, 기타·연금소득금액, 이자·배당)"]) \
            if BARE_INCOME.search(text) else None

    missing = []
    if method == "단순경비율" and simple_rate is None:
        missing.append("업종의 단순경비율(국세청 고시, 홈택스 '기준·단순경비율 조회')")
    if method == "기준경비율" and (standard_rate is None or simple_rate is None or major is None):
        missing.append("기준경비율 계산에 필요한 업종의 기준경비율·단순경비율과 주요경비(매입·임차료·인건비) 금액")
    if method != "장부" and revenue is None:
        missing.append("사업 총수입금액")
    if deposits is not None and houses is None:
        missing.append("임대하는 주택 수(40㎡ 이하·기준시가 2억원 이하 소형주택 제외, 간주임대료는 3주택 이상 또는 "
                       "2주택·보증금 12억원 초과일 때만)")
    if daily is not None and days is None:
        missing.append("일용근로 일한 날수")
    if gross_only.get("연금소득") is not None and other is None:
        gross_only["연금소득"] = None
        missing.append("연금의 종류(국민연금 등 공적연금인지, 연금저축·IRP 등 사적연금인지)와 1년 총연금액")
    if method == "장부" and revenue is not None and expense is None:
        missing.append("사업소득 필요경비(이미 경비를 뺀 금액이면 '사업소득금액'으로 알려주세요)")
    if wage_amount is not None and wage is None:
        missing.append("근로소득 총급여액(근로소득공제 전 금액, 근로소득세액공제 한도를 정합니다)")
    for name, value in gross_only.items():
        if value is not None and other is None:
            missing.append(f"{name}금액({name}에서 필요경비·{name}공제를 뺀 금액) 또는 종류(강연료·원고료 등은 "
                           "필요경비 60% 의제)")
    if missing:
        return MissingInputs(missing)
    if expense is not None and revenue is None and method == "장부":
        return None

    params = {"income": revenue or business_amount or 0, "expense": expense or 0, "wage_income": wage or 0,
              "other_income": other or 0, "interest_income": 0, "non_business_interest": 0,
              "dividend_gross_up": 0, "dividend_other": 0, "withheld": True,
              "personal_deduction_count": 1, "other_deductions": 0, "itemized_special_credits": False,
              "sincere_business": bool(SINCERE.search(text)), "other_tax_credits": credits or 0,
              "prepaid_tax": prepaid or 0, "business_method": method,
              "simple_rate": simple_rate or 0, "simple_excess_rate": excess_rate, "standard_rate": standard_rate or 0,
              "major_expenses": major or 0, "double_entry": bool(re.search(r"복식부기", text)),
              "pension_income": public_pension or 0, "private_pension": private_pension or 0, "pension_age": age or 0,
              "misc_income": fee or 0, "misc_expense_rule": "60%" if fee else "실제", "misc_expenses": 0,
              "rental_income": rental or 0, "rental_expenses": rental_expense or 0,
              "registered_rental": bool(REGISTERED.search(text)), "daily_wage": daily or 0,
              "daily_work_days": days or 0, "rental_deposits": deposits or 0, "rental_house_count": houses or 0,
              "religious_income": religious or 0,
              "religious_as_wage": bool(religious) and bool(RELIGIOUS_AS_WAGE.search(text))}
    if method != "장부":
        params["expense"] = 0
    params.update(financial)
    assumptions = list(financial_assumptions)
    if method != "장부":
        assumptions.append(f"장부 없이 {method}로 사업소득금액을 추계했습니다(경비율은 말씀하신 국세청 고시 값).")
    if fee:
        assumptions.append("강연료·원고료 등은 받은 금액의 60%를 필요경비로 보았고(실제 경비가 더 크면 그 금액), 원천징수 20%가 "
                           "된 것으로 보았습니다. 기타소득금액이 300만원 이하면 분리과세와 종합과세 중 적은 쪽을 골랐습니다.")
    if private_pension:
        assumptions.append("사적연금은 연금수령분이 원천징수된 것으로 보고, 법이 허용하는 분리과세와 종합과세 중 적은 쪽을 골랐습니다.")
    if rental:
        assumptions.append("주택임대 총수입금액이 2천만원 이하면 분리과세(14%)와 종합과세 중 적은 쪽을 골랐습니다"
                           + ("." if rental_expense is not None else "(임대 필요경비를 말하지 않아 종합과세 쪽은 0원으로 비교)."))
    if deposits:
        assumptions.append(f"보증금 합계 {deposits:,}원을 1년 내내 받은 것으로 보고 임대 주택은 {houses}채(소형주택 제외)로 "
                           "보았습니다. 보증금 운용으로 생긴 이자·배당은 없다고 보았습니다.")
    if religious:
        assumptions.append("종교인소득은 비과세 소득(학자금·식사대 등)을 뺀 금액으로 보았고, "
                           + ("근로소득으로 신고해 총급여에 더했습니다." if params["religious_as_wage"] else
                              "기타소득으로 신고해 필요경비 표(80~20%)를 적용했습니다. 근로소득으로 신고할 수도 있습니다."))
    if daily:
        assumptions.append("일용근로소득은 매일 지급받아 원천징수로 과세가 끝나는 것으로 보았습니다.")
    if wage is not None and re.search(r"연봉|(?<!총)급여", text):
        assumptions.append("연봉(급여)은 비과세소득을 뺀 총급여액으로 보았습니다.")
    if business_amount is not None:
        assumptions.append("사업소득금액은 필요경비를 이미 뺀 금액으로 보았습니다.")
    unnamed = [name for name, present in (("근로소득", wage or daily), ("사업소득", revenue or business_amount or rental or deposits),
                                           ("기타·연금소득", other or fee or public_pension or private_pension or religious),
                                           ("금융소득", financial or None))
               if not present]
    if unnamed:
        assumptions.append("말씀하신 소득 외에 " + "·".join(unnamed) + "은 없다고 보았습니다.")
    count, count_note = _count(texts)
    if deductions is not None:
        params["personal_deduction_count"], params["other_deductions"] = 0, deductions
        assumptions.append(f"종합소득공제는 말씀하신 합계 {deductions:,}원(기본공제 포함)으로 계산했습니다.")
    elif count is not None:
        params["personal_deduction_count"] = count
        assumptions.append(count_note or f"기본공제 {count}명(본인 포함)을 반영했습니다.")
        assumptions.append("기본공제 외 추가공제·연금보험료공제 등 다른 소득공제는 반영하지 않았습니다.")
    else:
        assumptions.append(f"종합소득공제는 본인 기본공제 1명({basic_deduction:,}원)만 반영했습니다. "
                           "부양가족·연금보험료 등 다른 공제가 있으면 세금이 줄어듭니다.")
    if credits is None:
        assumptions.append("자녀·연금계좌·보험료·의료비·교육비 세액공제 등 그 밖의 세액공제는 반영하지 않았습니다.")
    if financial:
        withheld = withholding_stated(text)
        if withheld is None:
            assumptions.append("금융소득이 국내에서 원천징수되었다고 가정했습니다.")
        else:
            params["withheld"] = withheld
    return StatedInputs(params, assumptions)

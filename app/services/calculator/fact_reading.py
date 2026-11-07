"""Read a calculation conversation into calculator facts: the model finds them, code proves each one.

The regex readers know fixed phrasings, while people say "2014년 매입해서 2019년까지 거주", "서초구
반포동", "집은 이거 하나야" or just "네". Here the model lists the facts a calculator needs, each with the
user's own words (`quote`), and a fact is used only when code can check it against those words:

- the quote is the user's words verbatim (spacing aside), or a 네/아니요 reply to the fact last asked;
- money equals an amount written in the quote, or the sum of the amounts there (a stated total);
- a date has its year (and month) in the quote, or a relative word (작년, 지난달, 지금까지);
- a period in years or months is written in the quote; a period given as dates is counted here, never
  by the model;
- a count, an age or a choice (1주택, 관계, 비사업용 …) has its number or one of its cue words there.

Proven facts become the standard sentences the readers already parse ("거주기간 5년"), so the readers
still decide what is missing and what is assumed. A fact that fails its proof is dropped and reported.
"""
import calendar
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import Field

from app.schemas.ai_output import AIOutput
from app.services.calculator.financial_inputs import _MONEY, parse_money

logger = logging.getLogger(__name__)

YES = re.compile(r"^\s*(?:네|예|응|어|맞(?:아|아요|습니다|음|다)?|그래|그렇(?:습니다|다|죠|어)?|ㅇㅇ|yes)(?![가-힣a-z])", re.I)
NO = re.compile(r"^\s*(?:아니|아뇨|아님|ㄴㄴ|no)(?![a-z])", re.I)
NOW = re.compile(r"지금|현재|아직|오늘|이번\s*달|요즘|계속\s*(?:살|거주)")

HOUSE = r"아파트|주택|빌라|다세대|연립|단독|(?<![가-힣])집(?![합중계값])"
ONE_HOME = (r"1\s*세대\s*1\s*주택|1\s*가구\s*1\s*주택|(?<![\d가-힣])1\s*주택|일\s*주택|한\s*채|하나(?:뿐|밖에|만)?|유일|"
            r"이것?\s*(?:뿐|하나)|이거\s*하나|다른\s*(?:집|주택)(?:은|이|도)?\s*없")
MULTI_HOME = r"다주택|(?<!\d)[2-9]\s*주택|두\s*채|세\s*채|[2-9]\s*채|여러\s*채|1\s*주택(?:이|은|자)?\s*(?:가\s*)?아니"
ADJUSTED = r"조정\s*(?:대상)?\s*지역"
NOT_ADJUSTED = r"비\s*조정|조정\s*(?:대상\s*)?지역(?:이|은|에|도)?\s*(?:아니|아닌|아닙|아냐|해제|빠)"
SPOUSE = r"배우자|아내|남편|와이프|부인|(?:어머니|엄마|아버지|아빠)(?:와|랑|하고|,|\s*및|(?:는|가|께서)\s*(?:살아|생존|계시))"
# The person who died is also named with 돌아가셨다; only an earlier death or both parents mark the spouse as gone.
NO_SPOUSE = (r"부모님?(?:이|께서|은|는)?\s*(?:모두|다|두\s*분\s*(?:다|모두)?)?\s*(?:돌아가|사망|별세)|"
             r"배우자(?:는|가|도)?\s*(?:없|안\s*계|먼저|이미)|"
             r"(?:어머니|아버지|엄마|아빠)(?:도\s*|(?:는|가)?\s*(?:이미|먼저|예전에)\s*)(?:돌아가|사망|별세)|"
             r"미혼|이혼|혼자\s*(?:사셨|살)")
PARENT = r"(?<![할외시])(?:아버지|어머니|아버님|어머님)|아빠|엄마|(?<![조외])부모|부친|모친"
GRANDPARENT = r"할아버지|할머니|조부모|조부|조모|외할아버지|외할머니|외조부"
CHILD = r"아들|딸|(?<!손)자녀|자식"
GRANDCHILD = r"손자|손녀|손주"
RELATIVE = r"삼촌|숙부|이모|고모|외삼촌|형|누나|오빠|언니|동생|형제|자매|장인|장모|시아버지|시어머니|사위|며느리|조카|사촌|친척|친족"
STRANGER = r"친구|지인|애인|타인|남(?:한테|에게|이)|모르는\s*사람|회사"
MINOR_WORDS = r"미성년|초등|중학생|고등학생|유치원|아기|갓난|(?<!\d)(?:[0-9]|1[0-8])\s*(?:살|세(?![금액율]))"
ADULT_WORDS = (r"(?<!미)성년|성인|대학생|직장인|사회초년생|군인|결혼|혼인|(?<!\d)(?:19|[2-9]\d)\s*(?:살|세(?![금액율]))|"
               r"스무|스물|서른|마흔|쉰|예순|일흔|여든")

# Cue words a quote must contain for a choice. A true value also must not carry its false cue, which is
# often its negation ("조정대상지역 아니야" holds both).
CHOICES = {
    "asset_type": {"주택": HOUSE, "토지·건물": r"토지|땅|임야|상가|건물|공장|창고|나대지|논|밭",
                   "주식": r"주식|지분|상장|코스피|코스닥", "분양권": r"분양권", "조합원입주권": r"입주권"},
    "is_one_home": {"true": ONE_HOME, "false": MULTI_HOME},
    "lived": {"false": r"(?:거주|실거주|살)(?:하지|지|은|는)?\s*(?:않|안\s*(?:했|함|하|살))|거주\s*(?:안|없)|안\s*살|"
                       r"한\s*번도\s*(?:안|살지)"},
    "acquired_in_adjusted_area": {"true": ADJUSTED, "false": NOT_ADJUSTED},
    "adjusted_on_transfer": {"true": ADJUSTED, "false": NOT_ADJUSTED},
    "surcharge": {"true": r"중과\s*(?:대상|적용|된다|돼|받)", "false": r"중과\s*(?:배제|제외|대상\s*(?:이\s*)?아니|안\s*(?:돼|되|받))"},
    "non_business_land": {"true": r"비사업용|사업(?:용)?(?:으로|에)?\s*(?:쓴\s*적|사용한\s*적|이용한\s*적|쓰지|사용하지|안\s*쓴)|"
                                  r"놀리|방치|빈\s*땅|나대지|그냥\s*(?:두|갖고|가지고|보유)|투자용",
                          "false": r"사업용\s*(?:토지|으로\s*(?:썼|사용했|쓰고))|농사|자경|공장\s*부지|사업장"},
    "stock_market": {"국내상장": r"(?<!비)상장|코스피|코스닥|증시|유가증권", "국내비상장": r"비상장|장외",
                     "국외": r"해외|미국|국외|나스닥|외국"},
    "major_shareholder": {"true": r"(?<!소액)대주주", "false": r"소액|개미|대주주(?:가|는|이)?\s*아니|일반\s*투자자"},
    "has_spouse": {"true": SPOUSE, "false": NO_SPOUSE},
    "relation": {"배우자": r"배우자|남편|아내|와이프|부인", "직계존비속": "|".join((PARENT, GRANDPARENT, CHILD, GRANDCHILD)),
                 "기타친족": RELATIVE, "기타": STRANGER},
    "is_minor": {"true": MINOR_WORDS, "false": ADULT_WORDS},
    "is_simplified": {"true": r"간이", "false": r"일반\s*과세|일반\s*사업자"},
    "marriage_birth": {"true": r"2\s*년\s*(?:이내|안)|(?:결혼|혼인|출산)\s*(?:을\s*)?(?:예정|앞두|준비)|"
                               r"(?:결혼|혼인|출산|태어난|낳은)\s*(?:한\s*)?지\s*(?:1\s*년|\d{1,2}\s*개월)",
                       "false": r"(?:결혼|혼인)(?:한\s*지)?\s*(?:[3-9]|\d{2})\s*년|오래\s*(?:전|됐)"},
}


@dataclass(frozen=True)
class Spec:
    kind: str   # money | date | years | months | count | dependents | age | choice | place | name
    about: str


FIELDS = {
    "capital_gains": {
        "transfer_price": Spec("money", "판(팔) 금액, 양도가액"),
        "acquisition_price": Spec("money", "산 금액, 취득가액"),
        "expenses": Spec("money", "필요경비(취득세·중개수수료·수리비 등)"),
        "acquisition_date": Spec("date", "산 날짜"),
        "transfer_date": Spec("date", "판(팔) 날짜"),
        "holding_years": Spec("years", "보유기간을 연수로 직접 말한 경우"),
        "residence_years": Spec("years", "거주기간을 연수로 직접 말한 경우"),
        "residence_months": Spec("months", "거주기간을 개월로 말한 경우"),
        "residence_start": Spec("date", "거주를 시작한 날짜(산 때부터 살았으면 산 날짜)"),
        "residence_end": Spec("date", "거주를 끝낸 날짜(지금도 살면 now)"),
        "lived": Spec("choice", "보유하는 동안 한 번도 거주하지 않았으면 false"),
        "asset_type": Spec("choice", "판 자산: 주택(아파트·빌라·집 포함), 토지·건물, 주식, 분양권, 조합원입주권"),
        "is_one_home": Spec("choice", "판 날 세대가 가진 주택이 이 집 하나뿐이면 true, 두 채 이상이면 false"),
        "homes": Spec("count", "판 날 세대가 가진 주택 수(이 집 포함)"),
        "house_location": Spec("place", "판 집·땅이 있는 지역(시·구·동 등 사용자가 말한 그대로)"),
        "acquired_in_adjusted_area": Spec("choice", "산 당시 조정대상지역이었는지(true/false)"),
        "adjusted_on_transfer": Spec("choice", "판 날 조정대상지역인지(true/false)"),
        "surcharge": Spec("choice", "다주택 중과 대상인지(true/false)"),
        "non_business_land": Spec("choice", "사업에 쓰지 않은 토지(비사업용)인지(true/false)"),
        "stock_market": Spec("choice", "주식 구분: 국내상장, 국내비상장, 국외"),
        "major_shareholder": Spec("choice", "주식의 대주주인지(true/false)"),
        "stock_name": Spec("name", "판 주식의 회사 이름(말한 그대로)"),
    },
    "inheritance": {
        "estate_value": Spec("money", "상속재산 전체 금액(여럿을 말했으면 합계)"),
        "debts": Spec("money", "돌아가신 분의 채무"),
        "financial_assets": Spec("money", "상속재산 중 예금·주식 등 금융재산"),
        "spouse_inheritance": Spec("money", "배우자가 실제로 받는 몫"),
        "prior_gifts": Spec("money", "돌아가시기 전 10년 안에 상속인에게 증여한 재산"),
        "has_spouse": Spec("choice", "돌아가신 분의 배우자가 살아 있어 상속인인지(true/false)"),
        "children_count": Spec("count", "돌아가신 분의 자녀 수(말한 사람 수)"),
        "death_date": Spec("date", "돌아가신 날짜"),
    },
    "gift": {
        "gift_amount": Spec("money", "이번에 받는(주는) 증여 금액"),
        "prior_gifts_10y": Spec("money", "10년 안에 같은 사람에게 받은 이전 증여 금액"),
        "debts": Spec("money", "증여와 함께 넘겨받는 채무"),
        "relation": Spec("choice", "주는 사람과 받는 사람의 관계: 배우자, 직계존비속(부모·조부모와 자녀·손자녀), 기타친족, 기타"),
        "recipient_age": Spec("age", "받는 사람의 나이"),
        "is_minor": Spec("choice", "받는 사람이 미성년자인지(true/false)"),
        "marriage_birth": Spec("choice", "혼인신고일 전후 2년 또는 자녀 출생 후 2년 안에 받는 증여인지(true/false)"),
        "gift_date": Spec("date", "증여한 날짜"),
    },
    "vat": {
        "sales": Spec("money", "그 과세기간의 매출"),
        "purchases": Spec("money", "세금계산서·카드 등으로 받은 매입(재료비·임대료 등)"),
        "is_simplified": Spec("choice", "간이과세자이면 true, 일반과세자이면 false"),
    },
    "retirement": {
        "retirement_pay": Spec("money", "퇴직금"),
        "service_years": Spec("years", "근속연수를 연수로 직접 말한 경우"),
        "service_start": Spec("date", "입사 날짜"),
        "service_end": Spec("date", "퇴사 날짜"),
        "pension_transfer": Spec("money", "IRP 등 연금계좌로 옮긴 퇴직금"),
    },
    "income_tax": {
        "wage_income": Spec("money", "근로소득 총급여(연봉)"),
        "income": Spec("money", "사업소득 수입금액(프리랜서 수입 포함)"),
        "expense": Spec("money", "사업 필요경비"),
        "dependents": Spec("dependents", "본인을 뺀 부양가족 수(없으면 0)"),
    },
}
TOOLS = tuple(FIELDS)
TOOL_CUES = {
    "capital_gains": r"양도|매도|팔|판\s*(?:돈|금액|값)|처분",
    "inheritance": r"상속|유산|돌아가|사망|별세|물려\s*받",
    "gift": r"증여|주(?:셨|시|신|었|고|면|려)|줬|준대|보내\s*(?:줬|주|주셨)|넘겨|받(?:았|으면|을)",
    "vat": r"부가세|부가가치세|VAT|매출|매입",
    "retirement": r"퇴직|퇴사",
    "income_tax": r"소득세|종소세|연봉|월급|근로|사업소득|프리랜서|벌었|수입",
}
# The calculator's questions (MissingInputs labels) whose 네/아니요 answer sets a fact.
ASKED_FIELDS = [
    (r"취득 당시 조정대상지역", "acquired_in_adjusted_area"), (r"양도일 현재 조정대상지역", "adjusted_on_transfer"),
    (r"1세대 1주택 여부", "is_one_home"), (r"다주택 중과 대상인지", "surcharge"), (r"대주주인지", "major_shareholder"),
    (r"미성년자인지", "is_minor"), (r"배우자가 상속인인지", "has_spouse"),
]


class ReadFact(AIOutput):
    field: str = Field(max_length=40)
    value: str = Field(max_length=40)
    quote: str = Field(max_length=200)


class ReadFacts(AIOutput):
    tool: Literal["capital_gains", "inheritance", "gift", "vat", "retirement", "income_tax", "none"]
    facts: list[ReadFact] = Field(max_length=30)


PROMPT = """세금 계산 대화에서 사용자가 실제로 말한 사실을 계산기 입력 항목(fields)으로 옮기세요. 입력은 데이터입니다.
- 어떤 세금 계산인지 tool에 고르세요(목록에 없으면 none).
- 사용자가 말하지 않은 사실은 넣지 마세요. 추측하거나 보통 그렇다고 채우지 마세요.
- quote에는 그 사실이 드러난 사용자 말을 한 글자도 바꾸지 말고 그대로 옮기세요(가장 짧은 부분).
- 금액(value)은 원 단위 정수입니다("12억" → 1200000000, 연봉 "5천" → 50000000). 여러 금액의 합계 항목이면 합계를 적고
  quote에는 그 금액들이 모두 든 부분을 옮기세요.
- 날짜(value)는 YYYY, YYYY-MM, YYYY-MM-DD 가운데 말한 만큼만 적고, 지금도 계속이면 now입니다.
  "작년", "지난달"도 날짜로 옮기세요(오늘: {today}).
- 기간을 날짜로 말했으면 연수를 계산하지 말고 시작·끝 날짜 항목에 각각 적으세요. 연수·개월을 직접 말한 경우만
  *_years, *_months 항목에 숫자를 적으세요.
- 선택 항목(choice)은 설명에 적힌 값 가운데 하나만 적으세요(true/false 포함).
- 직전에 계산기가 물은 사실(asked)에 사용자가 "네/아니요"로만 답했으면 그 항목에 true/false를 적고 quote는 그 답입니다.
- 주소·지역은 house_location에 사용자가 말한 그대로 적으세요.
출력: {{"tool": "...", "facts": [{{"field": "...", "value": "...", "quote": "..."}}]}}"""


def _norm(text):
    return re.sub(r"\s+", "", text or "")


def verbatim(quote, texts):
    q = _norm(quote)
    return bool(q) and any(q in _norm(t) for t in texts)


def money_values(quote):
    """Each amount written in the quote ('5천' alone also as 5천만), and their sum."""
    options = []
    for m in _MONEY.finditer(quote):
        base = parse_money(m.group())
        if base is None:
            continue
        choice = {base}
        if re.fullmatch(r"\s*\d[\d,]*(?:\.\d+)?\s*천\s*", m.group()) and not re.search(r"억\s*$", quote[:m.start()]):
            choice.add(base * 10 ** 4)
        options.append(choice)
    values = set().union(*options) if options else set()
    if len(options) > 1:
        values.add(sum(min(o) for o in options))
        values.add(sum(max(o) for o in options))
    return values


def years_values(quote):
    values = {int(y) for y, _ in re.findall(r"(?<!\d)(\d{1,2})\s*년(?!\s*\d{1,2}\s*월)(\s*\d+\s*개월)?", quote)}
    if re.search(r"(?<!\d)1\s*년\s*반", quote):
        values.add(1)
    return values


def months_values(quote):
    values = {int(m) for m in re.findall(r"(\d+)\s*개월", quote)}
    values |= {int(y) * 12 + int(m) for y, m in re.findall(r"(?<!\d)(\d{1,2})\s*년\s*(\d+)\s*개월", quote)}
    if re.search(r"(?<!\d)1\s*년\s*반", quote):
        values.add(18)
    return values


NUMBER_WORDS = {"하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7,
                "여덟": 8, "아홉": 9, "열": 10}
COUNTED = r"\s*(?:명|채|분|사람|아이|애|자녀|아들|딸|형제|남매|자매)"
PEOPLE = (r"(?<![가-힣])(?:나|저|본인|제가|내가|아내|와이프|남편|배우자|부인|애|아이|아들|딸|자녀|동생|형|누나|오빠|언니|"
          r"막내|큰애|작은애)(?![가-힣]{2})")


def count_values(quote):
    values = {int(d) for d in re.findall(r"(\d+)" + COUNTED, quote)}
    values |= {int(a) + int(b) for a, b in re.findall(r"(\d+)\s*(?:남|녀)\s*(\d+)\s*(?:녀|남)", quote)}
    values |= {NUMBER_WORDS[w] for w in re.findall(r"(?<![가-힣])(하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)(?![가-힣]{2})", quote)}
    values |= {NUMBER_WORDS[w] for w in re.findall(r"(?<![가-힣])(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)" + COUNTED, quote)}
    people = len(re.findall(PEOPLE, quote))
    if people:
        values |= {people, people - 1}
    if re.search(r"외동", quote):
        values.add(1)
    if re.search(r"없", quote):
        values.add(0)
    return values


AGE_TENS = {"열": 10, "스무": 20, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50, "예순": 60, "일흔": 70, "여든": 80}
AGE_UNITS = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7,
             "여덟": 8, "아홉": 9}


def age_values(quote):
    values = {int(a) for a in re.findall(r"(?<!\d)(\d{1,3})\s*(?:살|세(?![금액율]))", quote)}
    for tens, unit in re.findall(r"(열|스무|스물|서른|마흔|쉰|예순|일흔|여든)\s*(한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉)?\s*살",
                                 quote):
        values.add(AGE_TENS[tens] + AGE_UNITS.get(unit, 0))
    return values


def date_proven(value, quote, today):
    """True when the quote writes the date (or the relative word that means it)."""
    if value == "now":
        return bool(NOW.search(quote))
    m = re.fullmatch(r"((?:19|20)\d{2})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", value)
    if not m:
        return False
    year, month, day = (int(g) if g else None for g in m.groups())
    relative_year = {"올해": today.year, "금년": today.year, "작년": today.year - 1, "지난해": today.year - 1,
                     "재작년": today.year - 2}
    previous = today.replace(day=1) - timedelta(days=1)
    relative_month = {r"이번\s*달": (today.year, today.month), r"지난\s*달": (previous.year, previous.month)}
    year_ok = bool(re.search(rf"{year}\s*(?:년|[.\-/])|(?<!\d)'?{year % 100:02d}\s*년", quote)) or any(
        word in quote and y == year for word, y in relative_year.items())
    if month is None:
        return year_ok
    month_ok = bool(re.search(rf"(?<!\d)0?{month}\s*월|{year}\s*[.\-/]\s*0?{month}(?!\d)", quote))
    for word, (y, mo) in relative_month.items():
        if re.search(word, quote) and (y, mo) == (year, month):
            year_ok = month_ok = True
    if day is not None and not re.search(rf"(?<!\d)0?{day}\s*일|[.\-/]\s*0?{day}(?!\d)", quote):
        return False
    return year_ok and month_ok


def choice_proven(field_name, value, quote):
    cues = CHOICES.get(field_name, {})
    pattern = cues.get(value)
    if pattern is None or not re.search(pattern, quote, re.I):
        return False
    if value == "true" and "false" in cues:
        return not re.search(cues["false"], quote, re.I)
    return True


@dataclass
class Proven:
    tool: str
    facts: dict = field(default_factory=dict)       # field -> value (typed)
    quotes: dict = field(default_factory=dict)      # field -> quote
    rejected: list = field(default_factory=list)    # (field, value, quote, reason)


def asked_fields(asked):
    """Boolean facts the calculator asked last."""
    return [name for pattern, name in ASKED_FIELDS if any(re.search(pattern, label) for label in asked or ())]


def _int(raw):
    digits = re.sub(r"[,\s원]", "", raw)
    return int(digits) if re.fullmatch(r"\d+", digits) else None


def _position(quote, texts):
    q = _norm(quote)
    for index in range(len(texts) - 1, -1, -1):
        found = _norm(texts[index]).rfind(q)
        if found >= 0:
            return index * 10 ** 6 + found
    return -1


NUMBERS = {"money": money_values, "years": years_values, "months": months_values, "count": count_values,
           "dependents": count_values, "age": age_values}


def prove(read: ReadFacts, texts, asked=(), today=None):
    """Keep the facts whose quote supports them; the rest are listed in `rejected`."""
    today = today or date.today()
    proven = Proven(read.tool)
    if read.tool not in FIELDS or not any(re.search(TOOL_CUES[read.tool], t, re.I) for t in texts):
        proven.tool = "none"
        return proven
    specs = FIELDS[read.tool]
    yes_no = asked_fields(asked)
    for fact in read.facts:
        spec = specs.get(fact.field)
        raw, quote, value = fact.value.strip(), fact.quote, None
        if spec is None:
            reason = "unknown_field"
        elif not verbatim(quote, texts):
            reason = "quote_not_in_conversation"
        else:
            short = len(_norm(quote)) <= 12
            reply = True if short and YES.search(quote) else False if short and NO.search(quote) else None
            if spec.kind == "choice" and reply is not None and yes_no == [fact.field] and raw == str(reply).lower():
                value = reply
            elif spec.kind in NUMBERS:
                number = _int(raw)
                value = number if number is not None and number in NUMBERS[spec.kind](quote) else None
            elif spec.kind == "date":
                value = raw if date_proven(raw, quote, today) else None
            elif spec.kind in ("place", "name"):
                value = quote.strip()
            elif spec.kind == "choice" and choice_proven(fact.field, raw, quote):
                value = True if raw == "true" else False if raw == "false" else raw
            reason = None if value is not None else "not_in_quote"
        if reason:
            proven.rejected.append((fact.field, fact.value, fact.quote, reason))
            continue
        if fact.field in proven.facts and proven.facts[fact.field] != value and \
                _position(quote, texts) < _position(proven.quotes[fact.field], texts):
            continue   # Two different proven values: the later words win, as in the readers.
        proven.facts[fact.field] = value
        proven.quotes[fact.field] = quote
    return proven


# ── dates and periods counted by code ──────────────────────────────────────────

def period(value, today):
    """(first, last) day a stated date can mean; 'now' is today."""
    if value == "now":
        return today, today
    parts = [int(p) for p in value.split("-")]
    if len(parts) == 3:
        day = date(*parts)
        return day, day
    if len(parts) == 2:
        return date(parts[0], parts[1], 1), date(parts[0], parts[1], calendar.monthrange(parts[0], parts[1])[1])
    return date(parts[0], 1, 1), date(parts[0], 12, 31)


def full_years(start, end):
    return max(end.year - start.year - ((end.month, end.day) < (start.month, start.day)), 0)


def full_months(start, end):
    return max((end.year - start.year) * 12 + end.month - start.month - (end.day < start.day), 0)


def years_between(start, end, *, round_up=False):
    """Possible whole years between two stated dates, fewest first."""
    (s1, s2), (e1, e2) = start, end
    if round_up:   # 근속연수: a part of a year counts as a year.
        low, high = full_months(s2, e1), full_months(s1, e2)
        return sorted({max(-(-low // 12), 1), max(-(-high // 12), 1)})
    return sorted({full_years(s2, e1), full_years(s1, e2)})


def won(value):
    return f"{value:,}원"


@dataclass
class Reading:
    """What the conversation states for one calculator, as the sentences its reader parses."""
    tool: str
    facts: dict
    quotes: dict
    lines: dict = field(default_factory=dict)      # key -> standard sentence
    notes: list = field(default_factory=list)      # how a fact was read, shown with the result
    options: dict = field(default_factory=dict)    # key -> [(facts to set, label)] when the words allow several
    derived: dict = field(default_factory=dict)    # counted values (holding, residence …)
    unclear: list = field(default_factory=list)    # what the conversation leaves open, to ask
    place: str | None = None

    def text(self, overrides=None):
        lines = {**self.lines, **(overrides or {})}
        resolved = [f"'{spoken}'은 {won(value)}" for spoken, value in self.resolved().items()]
        # Each sentence ends with a period: "보유기간 10년\n거주기간" would read as "10년 거주".
        return "\n".join(f"{line}." for line in [*[v for v in lines.values() if v], *resolved])

    def resolved(self):
        """'5천' after 연봉 proven as 5천만원: the reader must not ask its unit again."""
        out = {}
        for name, value in self.facts.items():
            spec = FIELDS[self.tool].get(name)
            if spec and spec.kind == "money" and name in self.quotes:
                for m in re.finditer(r"\d[\d,]*\s*천(?!\s*만|\s*원|\s*\d)", self.quotes[name]):
                    if parse_money(m.group()) * 10 ** 4 == value:
                        out[m.group().strip()] = value
        return out

    def understood(self):
        """The proven facts in the user's words, for a reply that still has to ask."""
        names = {name: re.sub(r"\s*\([^)]*\)", "", spec.about) for name, spec in FIELDS[self.tool].items()}
        return [names[name] + ': "' + self.quotes[name] + '"' for name in self.facts
                if name in names and name in self.quotes]


def reading(proven: Proven, *, transfer=None, today=None):
    """Turn proven facts into the reader's sentences, counting periods from dates."""
    today = today or date.today()
    r = Reading(proven.tool, dict(proven.facts), dict(proven.quotes))
    f, lines = r.facts, r.lines
    if r.tool == "capital_gains":
        _capital_gains(r, transfer, today)
    elif r.tool == "inheritance":
        for name, label in (("estate_value", "상속재산"), ("debts", "채무"), ("financial_assets", "금융재산"),
                            ("spouse_inheritance", "배우자 몫"), ("prior_gifts", "사전증여")):
            if name in f:
                lines[name] = f"{label} {won(f[name])}"
        if "has_spouse" in f:
            lines["spouse"] = "배우자 있음" if f["has_spouse"] else "배우자 없음"
        if "children_count" in f:
            lines["children"] = f"자녀 {f['children_count']}명" if f["children_count"] else "자녀 없음"
    elif r.tool == "gift":
        # "사전증여": a bare "증여 X원" would also be read as this gift's amount.
        for name, label in (("gift_amount", "증여액"), ("prior_gifts_10y", "사전증여"), ("debts", "채무")):
            if name in f:
                lines[name] = f"{label} {won(f[name])}"
        if "relation" in f:
            lines["relation"] = RELATION_LINES[f["relation"]]
        minor = f.get("is_minor")
        if minor is None and "recipient_age" in f and not 18 <= f["recipient_age"] <= 20:
            minor = f["recipient_age"] < 19
            r.notes.append(f"받는 사람이 {f['recipient_age']}살이라 {'미성년자' if minor else '성년'}로 보았습니다.")
        if minor is not None:
            lines["minor"] = "미성년" if minor else "성년"
        if "marriage_birth" in f:
            lines["marriage"] = "혼인 2년 이내 증여" if f["marriage_birth"] else "혼인·출산 공제 대상 아님"
    elif r.tool == "vat":
        for name, label in (("sales", "매출"), ("purchases", "매입액")):
            if name in f:
                lines[name] = f"{label} {won(f[name])}"
        if "is_simplified" in f:
            lines["simplified"] = "간이과세자" if f["is_simplified"] else "일반과세자"
    elif r.tool == "retirement":
        if "retirement_pay" in f:
            lines["pay"] = f"퇴직금 {won(f['retirement_pay'])}"
        years = [f["service_years"]] if "service_years" in f else None
        if years is None and "service_start" in f and "service_end" in f:
            years = years_between(period(f["service_start"], today), period(f["service_end"], today), round_up=True)
            r.notes.append(f"근속연수는 입사({f['service_start']})부터 퇴사({f['service_end']})까지 {'·'.join(map(str, years))}년으로 "
                           "셌습니다(1년 미만은 1년).")
        if years:
            lines["service"] = f"근속연수 {years[0]}년"
            if len(years) > 1:
                r.options["service"] = [({"service_years": y}, f"근속연수가 {y}년이면") for y in years]
        if "pension_transfer" in f:
            lines["pension"] = f"{won(f['pension_transfer'])}을 IRP로 이체"
    elif r.tool == "income_tax":
        for name, label in (("wage_income", "총급여"), ("income", "수입금액"), ("expense", "필요경비")):
            if name in f:
                lines[name] = f"{label} {won(f[name])}"
        if "dependents" in f:
            lines["count"] = f"기본공제 {f['dependents'] + 1}명"
            r.notes.append(f"기본공제 인원은 본인과 부양가족 {f['dependents']}명을 합해 {f['dependents'] + 1}명으로 보았습니다.")
    return r


RELATION_LINES = {"배우자": "배우자에게서 증여", "직계존비속": "부모에게서 증여", "기타친족": "친족에게서 증여", "기타": "타인에게서 증여"}


def _capital_gains(r, transfer, today):
    from app.services.calculator import adjusted_areas
    f, lines, notes = r.facts, r.lines, r.notes
    for name, label in (("transfer_price", "양도가액"), ("acquisition_price", "취득가액"), ("expenses", "필요경비")):
        if name in f:
            lines[name] = f"{label} {won(f[name])}"
    asset = f.get("asset_type")
    if asset:
        lines["asset"] = {"주택": "주택", "토지·건물": "토지", "주식": "주식", "분양권": "분양권", "조합원입주권": "조합원입주권"}[asset]
    if "transfer_date" in f and f["transfer_date"] != "now":
        sold = period(f["transfer_date"], today)
    elif transfer is not None:
        sold = (transfer, transfer)
    else:
        sold = (today, today)
        if "acquisition_date" in f and "holding_years" not in f:
            notes.append(f"양도일을 말하지 않아 오늘({today.isoformat()}) 판다고 보고 보유기간을 셌습니다.")
    r.derived["sold"] = sold
    bought = period(f["acquisition_date"], today) if "acquisition_date" in f else None
    holding = [f["holding_years"]] if "holding_years" in f else None
    if bought:
        counted = years_between(bought, sold)
        if holding is None:
            holding = counted
            notes.append(f"보유기간은 취득({f['acquisition_date']})부터 양도까지 만 {'·'.join(map(str, counted))}년으로 셌습니다"
                         + ("(날짜를 연·월까지만 말해 둘 다 가능)." if len(counted) > 1 else "."))
        elif holding[0] not in counted:
            notes.append(f"말씀하신 보유기간 {holding[0]}년과 취득 시기({f['acquisition_date']})로 센 기간(만 "
                         f"{'·'.join(map(str, counted))}년)이 다릅니다. 말씀하신 {holding[0]}년으로 계산했습니다.")
    residence = None
    if "residence_years" in f:
        residence = [f["residence_years"]]
    elif "residence_months" in f:
        residence = [f["residence_months"] // 12]
        notes.append(f"거주기간 {f['residence_months']}개월은 만 {residence[0]}년으로 보았습니다(1년 미만 버림).")
    elif ("residence_start" in f or "acquisition_date" in f) and "residence_end" in f:
        start = f.get("residence_start") or f["acquisition_date"]
        begin = period(start, today)
        if bought:   # 보유기간 중 거주기간: living there before buying it does not count.
            begin = (max(begin[0], bought[0]), max(begin[1], bought[1]))
        end = f["residence_end"]
        residence = years_between(begin, sold if end == "now" else period(end, today))
        notes.append(f"거주기간은 {start}부터 {'양도일' if end == 'now' else end}까지 만 {'·'.join(map(str, residence))}년으로 셌습니다"
                     + ("(날짜를 연·월까지만 말해 둘 다 가능)." if len(residence) > 1 else "."))
    elif f.get("lived") is False:
        residence = [0]
    if holding is None and residence and min(residence) >= 1 and asset in (None, "주택"):
        holding = [min(residence)]
        notes.append(f"보유기간을 말하지 않았지만 보유기간 중 {min(residence)}년 거주했으므로 보유기간을 최소 {min(residence)}년으로 "
                     "보았습니다(더 길면 장기보유특별공제가 커져 세금이 줄어듭니다).")
    if holding:
        lines["holding"] = f"보유기간 {holding[0]}년"
        if len(holding) > 1:
            r.options["holding"] = [({"holding_years": y}, f"보유기간이 만 {y}년이면") for y in holding]
        r.derived["holding"] = holding
    if residence is not None:
        if holding:
            residence = sorted({min(y, max(holding)) for y in residence})
        lines["residence"] = f"거주기간 {residence[0]}년"
        if len(residence) > 1:
            r.options["residence"] = [({"residence_years": y}, f"거주기간이 만 {y}년이면") for y in residence]
        r.derived["residence"] = residence
    one_home = f.get("is_one_home")
    homes = f.get("homes")
    if one_home is None and homes:
        one_home = homes == 1
    if one_home:
        lines["one_home"] = "1세대 1주택"
    elif one_home is False:
        lines["one_home"] = f"{homes}주택" if homes and homes >= 2 else "1세대 1주택이 아니야"
    place = r.place = f.get("house_location")
    area = adjusted_areas.find_area(place) if place else None
    r.derived["area"] = area
    if one_home is not False and asset in (None, "주택"):
        stated = f.get("acquired_in_adjusted_area")
        if stated is not None:
            lines["acquired_adjusted"] = "취득 당시 조정대상지역" if stated else "취득 당시 비조정"
        else:
            span = r.derived["bought"] = bought or _bought_from_holding(sold, holding)
            value, note = adjusted_areas.acquired_in_adjusted_area(area, span) if span else (None, None)
            if value is not None:
                lines["acquired_adjusted"] = "취득 당시 조정대상지역" if value else "취득 당시 비조정"
                notes.append(note)
            elif place and note:
                r.unclear.append(note)
    if one_home is False and asset in (None, "주택"):
        stated = f.get("adjusted_on_transfer")
        if stated is None and place:
            stated, note = adjusted_areas.adjusted_on_transfer(area, sold)
            (notes if stated is not None else r.unclear).append(note)
        if stated is not None:
            lines["transfer_adjusted"] = "양도일 현재 조정대상지역" if stated else "양도일 현재 비조정"
        if "surcharge" in f:
            lines["surcharge"] = "중과 대상" if f["surcharge"] else "중과 배제"
    if f.get("non_business_land"):
        lines["non_business"] = "비사업용 토지"
    if "stock_market" in f:
        lines["stock_market"] = {"국내상장": "국내 상장주식", "국내비상장": "비상장 주식", "국외": "해외 주식"}[f["stock_market"]]
    if "major_shareholder" in f:
        lines["major"] = "대주주" if f["major_shareholder"] else "소액주주"


def _bought_from_holding(sold, holding):
    """The acquisition span a holding period in whole years allows."""
    if not holding:
        return None
    def back(day, years):
        try:
            return day.replace(year=day.year - years)
        except ValueError:   # 29 February
            return day.replace(year=day.year - years, day=28)
    return back(sold[0], max(holding) + 1), back(sold[1], min(holding))


def conversation_payload(query, history, asked, tool_hint, today):
    """The model's input: the user's words, what the calculator asked last, and the fields it may fill."""
    turns = []
    for m in (history or [])[-8:]:
        content = str(m.get("content", ""))
        if m.get("role") == "user":
            turns.append({"role": "user", "text": content})
        elif m.get("role") == "assistant":
            turns.append({"role": "assistant", "text": content[:300] + ("…" if len(content) > 300 else "")})
    turns.append({"role": "user", "text": query})
    tools = [tool_hint] if tool_hint in FIELDS else list(FIELDS)
    fields_ = {t: {name: f"{spec.kind}: {spec.about}" for name, spec in FIELDS[t].items()} for t in tools}
    return {"today": today.isoformat(), "conversation": turns, "asked": list(asked or ()), "tool_hint": tool_hint,
            "fields": fields_}


async def read_facts(query, history, *, asked=(), tool_hint=None, today=None):
    """The model's fact list for the conversation (one structured call), or None when it is unavailable.

    Any failure leaves the readers' own result in place, so the chat still answers as before.
    """
    import asyncio
    from app.schemas.reliability import strict_schema
    from app.services.llm_client import call_llm_structured
    today = today or date.today()
    payload = conversation_payload(query, history, asked, tool_hint, today)
    try:
        async with asyncio.timeout(25):
            raw = await call_llm_structured(
                [{"role": "system", "content": PROMPT.format(today=today.isoformat())},
                 {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                strict_schema(ReadFacts), temperature=0, max_tokens=1500, purpose="fact_reading")
        return ReadFacts.model_validate(raw)
    except Exception as exc:
        logger.warning("Fact reading unavailable (%s)", type(exc).__name__)
        return None

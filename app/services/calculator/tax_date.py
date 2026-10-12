"""The date whose tax law a chat calculation applies: 귀속연도, 양도일, 증여일, 상속개시일, 퇴직일, 과세기간.

A date counts only when the words next to it say which event it is ("2023년 귀속", "2023년 3월에 팔았",
"증여일은 2024-05-01"), so "2015년에 샀다" never sets the law of a 2023 sale. A year or month without a day
uses its last day, and the result says so. Two different dates for the same event are not guessed between.
"""
import calendar
import re
from datetime import date

DATE = r"((?:19|20)\d{2})\s*(?:년|[.\-/])\s*(?:(\d{1,2})\s*(?:월|[.\-/])\s*(?:(\d{1,2})\s*일?)?)?"
EVENTS = {
    "income_tax": r"귀속|과세\s*연도|소득|연봉|총급여|사업|신고",
    "retirement": r"퇴직|퇴사|그만두",
    "capital_gains": r"양도|팔|매도|판매|처분",
    "gift": r"증여",
    "inheritance": r"상속|사망|돌아가",
    "vat": r"과세\s*기간|[12]\s*기|부가",
}
LABELS = {"income_tax": "귀속연도", "retirement": "퇴직일", "capital_gains": "양도일", "gift": "증여일",
          "inheritance": "상속개시일", "vat": "과세기간"}
VAT_TERM = re.compile(r"((?:19|20)\d{2})\s*년\s*([12])\s*기")


def _last_day(year, month=None, day=None):
    if day:
        return date(year, month, day)
    month = month or 12
    return date(year, month, calendar.monthrange(year, month)[1])


def stated_tax_date(tool, texts):
    """(date, note) for the latest turn that dates the taxed event, ('ambiguous', label) or None."""
    if tool not in EVENTS:
        return None
    event = EVENTS[tool]
    # "2020년에 산 아파트를 팔면": an acquisition between the date and the sale ends the link.
    # Another year in between belongs to another event; an amount ("10억에") does not end the link.
    gap = r"(?:(?!샀|사서|(?<![가-힣])산\s|취득|매수|구입|구매|분양|입사|(?:19|20)\d{2}\s*년)[^.\n]){0,20}?"
    after = re.compile(DATE + gap + r"(?:" + event + ")")
    before = re.compile(r"(?:" + event + r")\S{0,3}\s*(?:은|는|이|:)?\s*" + DATE)
    for text in reversed(texts):
        found = set()
        if tool == "vat":
            found |= {_last_day(int(y), 6 if term == "1" else 12) for y, term in VAT_TERM.findall(text)}
        for pattern in (() if found else (after, before)):
            for m in pattern.finditer(text):
                year, month, day = (int(g) if g else None for g in m.groups()[:3])
                try:
                    found.add(_last_day(year, month, day))
                except ValueError:
                    return "ambiguous", LABELS[tool]
        if len(found) > 1:
            return "ambiguous", LABELS[tool]
        if found:
            when = found.pop()
            exact = re.search(re.escape(str(when.year)) + r"\s*(?:년|[.\-/])\s*\d{1,2}\s*(?:월|[.\-/])\s*\d{1,2}", text)
            note = (f"{LABELS[tool]} {when.isoformat()}에 시행된 세법으로 계산했습니다."
                    + ("" if exact else " 날짜를 정확히 말하지 않아 그 기간의 마지막 날을 기준으로 했습니다."))
            return when, note
    return None

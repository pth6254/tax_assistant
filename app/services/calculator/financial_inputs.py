"""Korean money amounts and the financial-income part of a tax question.

`parse_money` and `stated_amount` read amounts such as "1억 5천만원" written after a label; the
capital gains and comprehensive income tax readers share them. `stated_financial_amounts` reads
interest, dividends and 비영업대금의 이익 from one turn and states the assumptions that complete
them (an unspecified 금융소득 is domestic deposit interest, a dividend is grossed up). Anything it
cannot read unambiguously makes the whole question unreadable (None).
"""
import re

AMOUNT_FIELDS = {
    "interest_income": r"이자소득|이자 소득|예금이자|예금 이자|이자",
    "non_business_interest": r"비영업대금의 이익|비영업대금이익|비영업대금",
    "dividend_gross_up": r"배당소득|배당",
}
TOTAL = r"금융소득|금융 소득"
# Conditions the calculator does not model; a guess here would be a wrong tax.
UNSUPPORTED = re.compile(r"출자공동사업자|비거주자|해외|국외|외국|외화|분리과세\s*상품|비과세|ISA|결손")
UNIT = {"억": 10 ** 8, "천만": 10 ** 7, "백만": 10 ** 6, "만": 10 ** 4, "천": 10 ** 3}
_MONEY = re.compile(r"(?:\d[\d,]*(?:\.\d+)?\s*(?:억|천만|백만|만|천)\s*)+(?:원)?|\d[\d,]*\s*원")
_PARTICLE = r"(?:\s|:|=|은|는|이|가|으로|로|만|이\s*있|이고)*"


def parse_money(text):
    """'1억 5천만원' and the spoken '1억 5천' -> 150000000; a bare number is not money."""
    total, found, previous = 0, False, None
    for number, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만|천)?", text):
        value = float(number.replace(",", ""))
        # After 억, "5천" is spoken for 5천만, never 5천원.
        scale = UNIT["천만"] if unit == "천" and previous == "억" else UNIT.get(unit, 1)
        total += value * scale
        found, previous = True, unit
    return int(round(total)) if found else None


def ambiguous_thousands(text):
    """'경비 7천' alone is spoken for 7천만원 as often as 7천원; only '1억 5천' is certain."""
    return [m.group(0).strip() for m in re.finditer(r"\d[\d,]*\s*천(?!\s*만|\s*원|\s*\d)", text)
            if not re.search(r"억\s*$", text[:m.start()])]


def stated_amount(label, text):
    """The amount written right after a label; None when absent, and an error when stated twice."""
    values = []
    for match in re.finditer(r"(?<![가-힣A-Za-z])(?:" + label + r")" + _PARTICLE + r"(" + _MONEY.pattern + r")", text):
        if re.match(r"\s*\d", text[match.end():]):
            raise ValueError("partial_amount")  # "1억 5000": the rest has no unit
        values.append(parse_money(match.group(1)))
    values = list(dict.fromkeys(values))
    if len(values) > 1:
        raise ValueError("conflicting_amounts")
    return values[0] if values else None


def withholding_stated(text):
    if re.search(r"원천징수\s*(?:되지|안\s*된|안\s*됐|없)", text):
        return False
    if re.search(r"원천징수\s*(?:된|됐|되었|됨)", text):
        return True
    return None


def stated_financial_amounts(text):
    """(amounts, assumptions) read from one turn; ({}, []) without any, None when unclear."""
    try:
        amounts = {field: stated_amount(label, text) for field, label in AMOUNT_FIELDS.items()}
        total = stated_amount(TOTAL, text)
    except ValueError:
        return None
    # "이자" also sits inside "비영업대금 이자" style phrases; an amount claimed by two
    # categories is ambiguous.
    stated = [v for v in amounts.values() if v is not None]
    if len(stated) != len(set(stated)) and len(stated) > 1:
        return None
    assumptions = []
    if total is not None:
        if stated:
            return None  # a total and its parts together: which one is meant is not certain
        amounts["interest_income"] = total
        assumptions.append(f"금융소득 {total:,}원을 국내 예금 이자(원천징수세율 14%)로 가정했습니다. "
                           "배당·비영업대금이익이 섞여 있으면 결과가 달라집니다.")
    if not any(amounts.values()):
        return {}, []
    if amounts["dividend_gross_up"]:
        assumptions.append("배당은 모두 배당가산(Gross-up) 대상인 내국법인 배당으로 가정했습니다.")
    return {field: value or 0 for field, value in amounts.items()}, assumptions

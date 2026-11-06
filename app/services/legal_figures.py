"""Rates, money thresholds and periods a legal claim states, compared with its cited text.

A wrong rate, threshold or deadline is the costliest kind of invented tax fact. Each figure the
claim states must appear in the official text it cites or in the question, after normalising the
ways statutes write it ("100분의 20" = "20%", "4천800만원" = "48,000,000원", "3월 이내" = "3개월 이내").

Only figures written with a unit are read; bare numbers and calendar dates are not figures here.
A cited text that holds a table as an image (rates often do) cannot be read, so its claims are not
checked for rates.
"""
import re

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)")
_FRACTION = re.compile(r"(100|1천|1,000|1000|1만|10,000|10000)\s*분\s*의\s*(\d+(?:\.\d+)?)")
_FRACTION_BASE = {"100": 100, "1천": 1000, "1,000": 1000, "1000": 1000, "1만": 10000, "10,000": 10000, "10000": 10000}
_MONEY = re.compile(r"((?:\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|십만|만|천)\s*)+(?:\d[\d,]*)?|\d[\d,]{3,})\s*원")
_UNITS = (("조", 10 ** 12), ("억", 10 ** 8), ("만", 10 ** 4))
# A period is a number with a unit and a word that makes it a span, not a date ("6월 1일").
_PERIOD = re.compile(r"(?<![\d.])(\d{1,3})\s*(일|개월|월|년)\s*(?=이내|이상|이하|미만|초과|간|동안|내에|이 지난|이 경과|경과|전부터|"
                     r"후|전|부터|까지|째|분)")
_IMAGE_TABLE = re.compile(r"<img\b", re.IGNORECASE)


def percents(text: str) -> set[float]:
    values = {float(m[1]) for m in _PERCENT.finditer(text)}
    for base, numerator in _FRACTION.findall(text):
        values.add(round(float(numerator) * 100 / _FRACTION_BASE[base], 6))
    return values


def _group(text: str) -> float:
    """'4천800' -> 4800, '8천' -> 8000, '12' -> 12: the number in front of 만/억/조."""
    total, rest = 0.0, text
    for unit, size in (("천", 1000), ("백", 100), ("십", 10)):
        if unit in rest:
            head, rest = rest.split(unit, 1)
            total += (float(head) if head else 1) * size
    return total + (float(rest) if rest else 0)


def _won(expression: str) -> int | None:
    """Korean statute amounts: '4천800만' = 48,000,000, '1억 2천만' = 120,000,000, '8,000만' = 80,000,000."""
    rest, total = re.sub(r"[\s,]", "", expression), 0.0
    try:
        for unit, size in _UNITS:
            if unit in rest:
                head, rest = rest.split(unit, 1)
                total += (_group(head) if head else 1) * size
        return round(total + (_group(rest) if rest else 0))
    except ValueError:
        return None


def amounts(text: str) -> set[int]:
    return {value for m in _MONEY.finditer(text) if (value := _won(m[1])) is not None and value >= 1000}


def periods(text: str) -> set[tuple[int, str]]:
    found = set()
    for number, unit in _PERIOD.findall(text):
        found.add((int(number), "개월" if unit == "월" else unit))
    return found


def unsupported_figures(claim_text: str, cited_text: str, query: str = "") -> list[str]:
    """Figures in the claim that neither the cited official text nor the question contains."""
    allowed = cited_text + "\n" + query
    missing = []
    if not _IMAGE_TABLE.search(cited_text):
        known = percents(allowed)
        missing += [f"{value:g}%" for value in sorted(percents(claim_text)) if value not in known]
    known_money = amounts(allowed)
    missing += [f"{value:,}원" for value in sorted(amounts(claim_text)) if value not in known_money]
    known_periods = periods(allowed)
    missing += [f"{n}{unit}" for n, unit in sorted(periods(claim_text)) if (n, unit) not in known_periods]
    return missing

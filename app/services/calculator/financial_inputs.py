"""Read a financial-income tax question into calculator inputs plus stated assumptions.

The chat check for calculators (`policy.check_proposal`) needs every value written by
the user. A question such as "금융소득으로 1억을 벌면 세금 얼마?" states one amount, so
this reader fills the rest with assumptions that are shown with the result:
an unspecified financial amount is domestic deposit interest withheld at 14%, there is
no other comprehensive income, and the only deduction is the taxpayer's own basic
deduction. Anything it cannot read unambiguously returns None, and the question goes to
the reference-formula path instead.
"""
from dataclasses import dataclass
import re

AMOUNT_FIELDS = {
    "interest_income": r"이자소득|이자 소득|예금이자|예금 이자|이자",
    "non_business_interest": r"비영업대금의 이익|비영업대금이익|비영업대금",
    "dividend_gross_up": r"배당소득|배당",
    "other_income": r"다른 종합소득금액|다른 종합소득|다른 소득금액|다른 소득|사업소득금액|근로소득금액",
    "income_deductions": r"종합소득공제|소득공제",
}
TOTAL = r"금융소득|금융 소득"
# Conditions the calculator does not model; a guess here would be a wrong tax.
UNSUPPORTED = re.compile(r"출자공동사업자|비거주자|해외|국외|외국|외화|분리과세\s*상품|비과세|ISA|결손")
UNIT = {"억": 10 ** 8, "천만": 10 ** 7, "백만": 10 ** 6, "만": 10 ** 4, "천": 10 ** 3}
_MONEY = re.compile(r"(?:\d[\d,]*(?:\.\d+)?\s*(?:억|천만|백만|만|천)\s*)+(?:원)?|\d[\d,]*\s*원")
_PARTICLE = r"(?:\s|:|=|은|는|이|가|으로|로|만|이\s*있|이고)*"


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


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


def stated_financial_inputs(query, history=None, *, basic_deduction=None):
    """Calculator params and the assumptions that complete them, or None when unsure."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    try:
        amounts = {field: stated_amount(label, query) for field, label in AMOUNT_FIELDS.items()}
        total = stated_amount(TOTAL, query)
    except ValueError:
        return None
    # "이자" also sits inside "비영업대금 이자" style phrases; an amount claimed by two
    # categories is ambiguous.
    stated = [v for k, v in amounts.items() if v is not None and k not in {"other_income", "income_deductions"}]
    if len(stated) != len(set(stated)) and len(stated) > 1:
        return None
    assumptions = []
    if total is not None:
        if any(amounts[k] is not None for k in ("interest_income", "non_business_interest", "dividend_gross_up")):
            return None  # a total and its parts together: which one is meant is not certain
        amounts["interest_income"] = total
        assumptions.append(f"금융소득 {total:,}원을 국내 예금 이자(원천징수세율 14%)로 가정했습니다. "
                           "배당·비영업대금이익이 섞여 있으면 결과가 달라집니다.")
    financial = [amounts[k] for k in ("interest_income", "non_business_interest", "dividend_gross_up")]
    if not any(financial):
        return None
    params = {
        "interest_income": amounts["interest_income"] or 0,
        "non_business_interest": amounts["non_business_interest"] or 0,
        "dividend_gross_up": amounts["dividend_gross_up"] or 0,
        "dividend_other": 0,
        "other_income": amounts["other_income"] or 0,
        "income_deductions": amounts["income_deductions"] if amounts["income_deductions"] is not None else 0,
        "withheld": True,
    }
    if amounts["dividend_gross_up"]:
        assumptions.append("배당은 모두 배당가산(Gross-up) 대상인 내국법인 배당으로 가정했습니다.")
    if amounts["other_income"] is None:
        assumptions.append("금융소득 외 다른 종합소득은 없다고 가정했습니다.")
    if amounts["income_deductions"] is None:
        if basic_deduction is None:
            return None
        params["income_deductions"] = basic_deduction
        assumptions.append(f"종합소득공제는 본인 기본공제 1명({basic_deduction:,}원)만 반영했습니다.")
    withheld = withholding_stated(text)
    if withheld is None:
        assumptions.append("금융소득이 국내에서 원천징수되었다고 가정했습니다.")
    else:
        params["withheld"] = withheld
    return StatedInputs(params, assumptions)

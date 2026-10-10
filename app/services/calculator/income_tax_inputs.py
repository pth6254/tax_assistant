"""Read a comprehensive income tax question into calculator inputs plus stated assumptions.

The kind of each income decides its deduction and credit, so it must be named: 총급여(연봉),
사업 수입금액과 필요경비 (or 사업소득금액), 기타·연금소득금액, and 이자·배당 금융소득. A bare
"소득 5천만원", business revenue without its expenses, or a 기타·연금소득 given before its own
deduction is asked back (MissingInputs) instead of guessed. What only lowers the tax when the user
has it (부양가족, 그 밖의 소득공제·세액공제, 이미 낸 세금) defaults to none, and each such default
is listed with the result. Anything the calculator does not model returns None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import (UNSUPPORTED as FINANCIAL_UNSUPPORTED, ambiguous_thousands,
                                                      stated_amount, stated_financial_amounts, withholding_stated)

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
    FINANCIAL_UNSUPPORTED.pattern + r"|일용|퇴직|양도|증여|상속|법인세|법인소득|주택임대|임대소득|월세|월급|월\s*급여|"
    r"공동사업|감면|가산세|분리과세|의료비|교육비|보험료|기부금|자녀세액|연금계좌|신용카드|중소기업|매월|월\s*소득")
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
    except ValueError:
        return None
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
    stated_kinds = [wage, revenue, business_amount, other, *gross_only.values(), wage_amount]
    if not financial and all(v is None for v in stated_kinds):
        # A bare "소득 5천만원" does not say which deduction and credit apply.
        return MissingInputs(["소득의 종류(근로소득 총급여액, 사업소득 수입금액과 필요경비, 기타·연금소득금액, 이자·배당)"]) \
            if BARE_INCOME.search(text) else None

    missing = []
    if revenue is not None and expense is None:
        missing.append("사업소득 필요경비(이미 경비를 뺀 금액이면 '사업소득금액'으로 알려주세요)")
    if wage_amount is not None and wage is None:
        missing.append("근로소득 총급여액(근로소득공제 전 금액, 근로소득세액공제 한도를 정합니다)")
    for name, value in gross_only.items():
        if value is not None and other is None:
            missing.append(f"{name}금액({name}에서 필요경비·{name}공제를 뺀 금액)")
    if missing:
        return MissingInputs(missing)
    if expense is not None and revenue is None:
        return None

    params = {"income": revenue or business_amount or 0, "expense": expense or 0, "wage_income": wage or 0,
              "other_income": other or 0, "interest_income": 0, "non_business_interest": 0,
              "dividend_gross_up": 0, "dividend_other": 0, "withheld": True,
              "personal_deduction_count": 1, "other_deductions": 0, "itemized_special_credits": False,
              "sincere_business": bool(SINCERE.search(text)), "other_tax_credits": credits or 0,
              "prepaid_tax": prepaid or 0}
    params.update(financial)
    assumptions = list(financial_assumptions)
    if wage is not None and re.search(r"연봉|(?<!총)급여", text):
        assumptions.append("연봉(급여)은 비과세소득을 뺀 총급여액으로 보았습니다.")
    if business_amount is not None:
        assumptions.append("사업소득금액은 필요경비를 이미 뺀 금액으로 보았습니다.")
    unnamed = [name for name, present in (("근로소득", wage), ("사업소득", revenue or business_amount),
                                           ("기타·연금소득", other), ("금융소득", financial or None))
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

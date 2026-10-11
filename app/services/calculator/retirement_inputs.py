"""Read a retirement income tax question into calculator inputs plus stated assumptions.

The retirement pay and the years of service must be written; years decide both deductions, so they
are asked when missing. Months of service round up to a year, as the law does. A payment moved into a pension
account (IRP) is read as `pension_transfer`, and its amount is asked when only the account is named. 임원 퇴직금
한도 and pre-2020 retirements are not modelled and return None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import _MONEY, ambiguous_thousands, parse_money

PAY = re.compile(r"(?:퇴직금|퇴직급여|퇴직소득|퇴직\s*수당|퇴직연금\s*일시금)[^\d\n,.]{0,10}?(" + _MONEY.pattern + r")")
YEARS = re.compile(r"(\d+)\s*년\s*(?:(\d+)\s*개월\s*)?(?:동안\s*|간\s*)?(?:근무|근속|다니|다닌|다녔|일하|일한|재직|일했)|"
                   r"근속\s*(?:연수|기간)?\s*(?:은|는|이|:)?\s*(\d+)\s*년(?:\s*(\d+)\s*개월)?")
MONTHS_ONLY = re.compile(r"(\d+)\s*개월\s*(?:동안\s*|간\s*)?(?:근무|근속|다니|다닌|다녔|일하|일한|재직|일했)")
PREPAID = re.compile(r"(?:원천징수|이미\s*낸|기납부)[^\d\n]{0,10}?(" + _MONEY.pattern + r")")
UNSUPPORTED = re.compile(r"임원|2019년|2018년|2017년|2016년|해외|비거주|명예퇴직\s*수당")
# 연금계좌(IRP 등)로 옮긴 몫의 퇴직소득세는 연금으로 받을 때까지 미뤄진다(제146조 제2항).
PENSION_ACCOUNT = r"(?:IRP|연금\s*계좌|개인형\s*퇴직연금|연금저축\s*계좌)"
PENSION = re.compile(PENSION_ACCOUNT + r"|과세\s*이연|연금으로\s*(?:받|수령)", re.I)
TRANSFER = re.compile(r"(" + _MONEY.pattern + r")\s*(?:을|를|은|는|만|만큼)?\s*" + PENSION_ACCOUNT
                      + r"(?:으로|로|에)?\s*(?:이체|옮|넣|입금|이전|보내|받)|"
                      + PENSION_ACCOUNT + r"(?:으로|로|에)?\s*(?:이체|옮긴|넣은|입금)?\s*(?:한|된)?\s*(?:금액|돈)?\s*(?:은|는|이|:)?\s*("
                      + _MONEY.pattern + r")", re.I)
WHOLE = re.compile(r"(?:전액|전부|모두|다)\s*" + PENSION_ACCOUNT + "|" + PENSION_ACCOUNT
                   + r"(?:으로|로|에)?\s*(?:전액|전부|모두|다)", re.I)


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def stated_retirement_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    pays = {parse_money(m.group(1)) for m in PAY.finditer(text)}
    if len(pays) != 1:
        return None
    pay = pays.pop()
    years = None
    if m := YEARS.search(text):
        whole, months = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        years = int(whole) + (1 if months and int(months) else 0)
    elif m := MONTHS_ONLY.search(text):
        years = -(-int(m.group(1)) // 12)
    if not years:
        return MissingInputs(["근속연수(입사일부터 퇴사일까지, 1년 미만은 1년으로 계산)"])
    transfer = 0
    if PENSION.search(text):
        amounts = {parse_money(next(g for g in m.groups() if g)) for m in TRANSFER.finditer(text)}
        if WHOLE.search(text):
            amounts.add(pay)
        if len(amounts) != 1:
            return MissingInputs(["연금계좌(IRP 등)로 옮긴(옮길) 퇴직급여 금액"])
        transfer = amounts.pop()
        if transfer > pay:
            return None
    prepaid = parse_money(m.group(1)) if (m := PREPAID.search(text)) else 0
    assumptions = [f"퇴직급여 {pay:,}원 전액이 과세대상(비과세 없음)이고 근속연수는 {years}년으로 보았습니다(1년 미만은 1년으로 올림)."]
    if transfer:
        assumptions.append(f"2020년 이후 퇴직하고 {transfer:,}원을 연금계좌로 옮겨 그 몫의 퇴직소득세를 미루는 것으로 보았습니다. "
                           "연금으로 받을 때 실제 수령 10년 이하분은 미룬 세금의 70%, 그 뒤는 60%·50%를 냅니다.")
    else:
        assumptions.append("2020년 이후 퇴직하고 퇴직금을 일시금으로 받는 것으로 보았습니다. 연금계좌로 옮겨 연금으로 받으면 "
                           "퇴직소득세의 50~70%만 냅니다.")
    if not prepaid:
        assumptions.append("회사가 원천징수한 세액은 없다고 보아 산출세액 전부를 납부할 세액으로 보였습니다.")
    return StatedInputs({"retirement_pay": pay, "service_years": years, "prepaid_tax": prepaid,
                         "pension_transfer": transfer}, assumptions)

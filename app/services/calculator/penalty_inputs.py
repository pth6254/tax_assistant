"""Read a penalty tax (가산세) question into calculator inputs plus stated assumptions.

The unpaid tax and what went wrong (무신고, 과소신고, or only late payment) must be written; the kind
decides the rate, so it is asked when missing. A delay given in days is used as is; a delay given in
months is read as the months after the deadline for the late or amended return (감면) and as 30 days
a month for 납부지연가산세, which the result states. 부정행위 is not assumed. Anything the calculator does
not model (세금계산서·지급명세서 가산세, 원천징수, 고지 후 체납 …) returns None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import _MONEY, ambiguous_thousands, parse_money, stated_amount

TAX = (r"미납세액|미납 세액|본세|납부할 세액|내야 할 세금|세액|세금|부가세|부가가치세|종합소득세|소득세|"
       r"양도소득세|양도세|증여세|상속세|법인세")
NOT_FILED = re.compile(r"무신고|신고(?:를)?\s*(?:안|못|않|하지\s*않|놓)|기한\s*후\s*신고|신고\s*기한(?:을|이)?\s*(?:놓|넘|지나)")
UNDER = re.compile(r"과소\s*신고|덜\s*신고|적게\s*신고|누락|수정\s*신고")
LATE_ONLY = re.compile(r"(?:신고는\s*했는데|신고만\s*하고)|납부(?:만)?\s*(?:를\s*)?(?:늦|안|못)|미납|체납|납부지연")
NEGLIGENT = re.compile(r"부정|사기|이중\s*장부|허위|가공|차명|은닉")
NOT_NEGLIGENT = re.compile(r"부정(?:행위)?\s*(?:은|는|이)?\s*(?:없|아니|안\s*했)\S*")
DAYS = re.compile(r"(\d+)\s*일\s*(?:늦|지연|지나|후|뒤|만에|동안|경과)|지연\s*일수\s*(?:는|:)?\s*(\d+)\s*일")
MONTHS = re.compile(r"(\d+)\s*(?:개월|달)\s*(?:늦|지연|지나|후|뒤|만에|이내|안에|동안)")
YEARS = re.compile(r"(\d+)\s*년\s*(?:늦|지연|지나|후|뒤|만에|동안)")
UNSUPPORTED = re.compile(r"세금계산서|계산서|지급명세서|원천징수|가산세\s*감면\s*신청|고지서|독촉|체납\s*처분|"
                         r"영세율|기장|장부\s*(?:의\s*)?(?:기록|보관|미작성|불성실)|사업자\s*등록|현금영수증|성실신고|증빙\s*불비|인지세")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def _verb_amount(text):
    values = {parse_money(m.group(1)) for m in re.finditer(
        r"(" + _MONEY.pattern + r")\s*(?:을|를|의)?\s*(?:신고|납부|안\s*내|못\s*내|미납|체납|덜\s*내|덜\s*신고|적게\s*신고|누락)", text)}
    if len(values) > 1:
        raise ValueError("conflicting_amounts")
    return values.pop() if values else None


def stated_penalty_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    try:
        tax = next((v for v in (stated_amount(TAX, t) or _verb_amount(t) for t in reversed(texts)) if v is not None), None)
    except ValueError:
        return None
    if tax is None:
        return None
    kinds = [kind for kind, pattern in (("무신고", NOT_FILED), ("과소신고", UNDER), ("납부지연", LATE_ONLY))
             if pattern.search(text)]
    if len(kinds) > 1 and "납부지연" in kinds:
        kinds.remove("납부지연")   # 무신고·과소신고에는 납부지연가산세가 함께 붙는다.
    if len(kinds) != 1:
        return MissingInputs(["무신고(신고하지 않음)인지, 과소신고(덜 신고)인지, 신고는 했고 납부만 늦었는지"])
    kind = kinds[0]
    days = int(m.group(1) or m.group(2)) if (m := DAYS.search(text)) else None
    months = int(m.group(1)) if (m := MONTHS.search(text)) else None
    if months is None and (m := YEARS.search(text)):
        months = int(m.group(1)) * 12
    if days is None and months is None:
        return MissingInputs(["법정 신고·납부기한이 지나고 며칠(몇 개월) 뒤에 신고·납부하는지"])

    assumptions = []
    if days is None:
        days = months * 30
        assumptions.append(f"납부지연 일수는 {months}개월을 {days}일(1개월 30일)로 계산했습니다. 실제 일수로 하루 0.022%가 붙습니다.")
    negligent = bool(NEGLIGENT.search(NOT_NEGLIGENT.sub("", text)))
    filed_within = 0
    if kind != "납부지연":
        filed_within = months if months is not None else -(-days // 30)
        if filed_within:
            assumptions.append(f"법정신고기한이 지나고 {filed_within}개월 안에 스스로 "
                               + ("기한 후 신고" if kind == "무신고" else "수정신고")
                               + "하는 것으로 보아 감면을 적용했습니다(세무서가 알고 고지하기 전이어야 합니다).")
        if not negligent:
            assumptions.append("부정행위(이중장부·허위증빙 등)는 없다고 보았습니다.")
        if kind == "무신고":
            assumptions.append("복식부기의무자·법인의 수입금액 기준 하한(1만분의 7)은 반영하지 않았습니다.")
    params = {"unpaid_tax": tax, "penalty_type": kind, "is_negligent": negligent and kind != "납부지연",
              "days_late": days, "filed_within_months": filed_within, "revenue": 0}
    return StatedInputs(params, assumptions)

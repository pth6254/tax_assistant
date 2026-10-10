"""Read an inheritance tax question into calculator inputs plus stated assumptions.

The estate and who inherits must be written: whether there is a spouse and how many children
decide the 일괄공제, the 배우자공제 and the spouse's legal share. Those are asked back when missing.
What the user does not mention is assumed in the direction that does not understate the tax:
the spouse is taken to inherit nothing (the 5억원 minimum), no part of the estate is financial,
nobody is a minor, elderly or disabled. Earlier gifts are added only when stated; a gift mentioned
without its amount is asked. Each default is listed with the result. Anything the calculator does
not model (손자녀 상속, 상속포기, 유증, 비거주자, 가업·영농 …) returns None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import _MONEY, ambiguous_thousands, parse_money, stated_amount

ESTATE_LABEL = r"상속재산가액|상속재산|상속 재산|유산|재산"
DEBT_LABEL = r"채무|빚|부채|대출"
FINANCIAL_LABEL = r"금융재산|예금|적금|현금|주식"
SPOUSE_RECEIVES = r"배우자 몫|배우자가 받는|배우자 상속분|어머니 몫|아버지 몫|엄마 몫|아빠 몫"
PRIOR_LABEL = r"사전증여|사전 증여|생전 증여|미리 증여|증여한 재산|증여"
INHERIT_VERB = r"(?:을|를|이|가)?\s*(?:상속|물려|남기|남겨|남긴)"
SPOUSE = re.compile(r"배우자|아내|남편|부인(?!과)|(?:어머니|엄마|아버지|아빠)(?:와|랑|하고|,|\s*및)|(?:어머니|엄마|아버지|아빠)는\s*(?:살아|생존)")
# The person who died is also named with 돌아가셨다; only an earlier death marks the spouse as gone.
DECEASED_SPOUSE = re.compile(r"배우자(?:도|는|가)?\s*(?:이미|먼저|예전에)?\s*(?:돌아가|사망|별세|안\s*계)|"
                             r"(?:어머니|엄마|아버지|아빠)(?:도\s*|(?:는|가)?\s*(?:이미|먼저|예전에)\s*)(?:돌아가|사망|별세)")
NO_SPOUSE = re.compile(r"배우자(?:는|가)?\s*(?:없|안\s*계)|미혼|이혼")
CHILDREN = re.compile(r"(?:자녀|자식|아들|딸|형제|남매|자매)(?:는|가|이|은)?\s*(\d+)\s*명|(\d+)\s*(?:남|녀)\s*(\d+)\s*(?:녀|남)|"
                      r"(?:자녀|자식|아이)(?:는|가)?\s*(?:한|하나|1)\s*명?|외동|(?<![가-힣])(?:하나|둘|셋|넷)뿐인\s*(?:자녀|아들|딸)")
NO_CHILDREN = re.compile(r"자녀(?:는|가)?\s*없|자식(?:은|이)?\s*없|무자녀")
KOREAN_COUNT = {"한": 1, "하나": 1, "1": 1, "둘": 2, "셋": 3, "넷": 4}
MINOR = re.compile(r"미성년|초등|중학생|고등학생|아기|(?<!\d)(?:[0-9]|1[0-8])\s*살")
SPECIAL = re.compile(r"장애|65\s*세|연로|노부모|동거")
UNSUPPORTED = re.compile(
    r"손자|손녀|손주|대습|상속\s*포기|포기|유증|사인증여|비거주|해외|국외|가업|영농|동거주택|한정승인|"
    r"증여세|양도|감정평가|연부연납|물납|재상속|여러\s*차례|공동상속인\s*간")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def _children(text):
    if NO_CHILDREN.search(text):
        return 0
    m = CHILDREN.search(text)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return int(m.group(2)) + int(m.group(3))
    word = re.search(r"한|하나|1|둘|셋|넷", m.group(0))
    return KOREAN_COUNT.get(word.group(0), 1) if word else 1


def _verb_amount(text):
    values = {parse_money(m.group(1)) for m in re.finditer(r"(" + _MONEY.pattern + r")\s*" + INHERIT_VERB, text)}
    if len(values) > 1:
        raise ValueError("conflicting_amounts")
    return values.pop() if values else None


def stated_inheritance_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    latest = lambda label: next((v for v in (stated_amount(label, t) for t in reversed(texts)) if v is not None), None)
    try:
        estate = next((v for v in (stated_amount(ESTATE_LABEL, t) or _verb_amount(t) for t in reversed(texts))
                       if v is not None), None)
        debts, financial = latest(DEBT_LABEL), latest(FINANCIAL_LABEL)
        spouse_amount, prior = latest(SPOUSE_RECEIVES), latest(PRIOR_LABEL)
    except ValueError:
        return None
    if estate is None:
        return None
    has_spouse = None if not (SPOUSE.search(text) or NO_SPOUSE.search(text) or DECEASED_SPOUSE.search(text)) else (
        bool(SPOUSE.search(text)) and not NO_SPOUSE.search(text) and not DECEASED_SPOUSE.search(text))
    children = _children(text)
    missing = []
    if has_spouse is None:
        missing.append("돌아가신 분의 배우자가 상속인인지(배우자공제 최소 5억원)")
    if children is None:
        missing.append("돌아가신 분의 자녀 수(자녀 1명당 5천만원 공제, 배우자 법정상속분)")
    if MINOR.search(text):
        missing.append("미성년 상속인의 나이(19세까지 남은 연수 x 1천만원 공제)")
    if re.search(r"증여", text) and prior is None:
        missing.append("돌아가시기 전 10년(상속인 아닌 사람은 5년) 안에 증여한 재산의 금액")
    if missing:
        return MissingInputs(missing)
    if SPECIAL.search(text) or not children and has_spouse is False:
        return None   # 연로자·장애인 공제나 직계존속 상속은 사실이 더 필요하다.
    if (debts or 0) > estate or (financial or 0) > estate or (spouse_amount or 0) > estate:
        return None

    params = {"estate_value": estate, "debts": debts or 0, "spouse_inheritance": spouse_amount or 0,
              "children_count": children, "has_spouse": has_spouse, "financial_assets": financial or 0,
              "prior_gifts": prior or 0, "funeral_expenses": 0}
    assumptions = [f"상속재산가액은 말씀하신 {estate:,}원(평가액, 보험금 등 포함)으로 보았습니다."]
    if has_spouse and spouse_amount is None:
        assumptions.append("배우자가 실제 상속받는 금액을 말하지 않아 배우자공제는 최소 5억원으로 계산했습니다. "
                           "배우자가 법정상속분까지 실제로 상속받으면 공제가 커져 세금이 줄어듭니다.")
    if financial is None:
        assumptions.append("상속재산 중 예금·주식 등 금융재산은 없다고 보아 금융재산 상속공제(최대 2억원)를 반영하지 않았습니다.")
    if debts is None:
        assumptions.append("채무·공과금은 없다고 보았습니다.")
    if prior is None:
        assumptions.append("돌아가시기 전 10년 안에 상속인에게 증여한 재산은 없다고 보았습니다. 있으면 합산되어 세금이 늘어납니다.")
    else:
        assumptions.append(f"사전증여 {prior:,}원은 상속인이 10년 안에 받은 증여로 보고 합산했으며, 그 증여세와 과세표준은 "
                           "입력하지 않아 증여세액공제를 하지 않았습니다.")
    assumptions.append("장례비용은 증빙 없이도 빼는 최소 500만원만, 미성년·65세 이상·장애인 상속인은 없다고 보아 반영했습니다.")
    return StatedInputs(params, assumptions)

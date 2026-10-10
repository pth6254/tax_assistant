"""Read a gift tax question into calculator inputs plus stated assumptions.

The gift amount and who gives it must be written: the relation decides the deduction, and a
grandparent's gift is surcharged. Whether a child receiving from a parent is a minor, and whether a
gift said to be for a wedding or a birth falls within the two-year window, are asked back instead of
guessed. Earlier gifts from the same giver are added with their tax estimated (and disclosed);
other facts that would only lower the tax (another gift that used the deduction, a late filing)
default to the usual case and are listed with the result. Anything the calculator does not model
returns None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import _MONEY, ambiguous_thousands, parse_money, stated_amount

SPOUSE = r"배우자|남편|아내|와이프"
PARENT = r"(?<![할외시])(?:아버지|어머니|아버님|어머님)|아빠|엄마|(?<![조외])부모|부친|모친"
GRANDPARENT = r"할아버지|할머니|조부모|조부|조모|외할아버지|외할머니|외조부"
CHILD = r"아들|딸|(?<!손)자녀|자식"
GRANDCHILD = r"손자|손녀|손주|외손자|외손녀"
RELATIVE = (r"삼촌|숙부|이모(?!티)|고모|외삼촌|형(?:님|이|에게|한테|으로부터|이랑)|누나|오빠|언니|동생|형제|자매|"
            r"장인|장모|시아버지|시어머니|사위|며느리|조카|사촌")
STRANGER = r"친구|지인|애인|타인"
GIVE = r"(?:을|를)?\s*(?:증여|물려|주|줬|준|받|넘겨|이전|송금|보내)"
AMOUNT_LABEL = r"증여재산가액|증여가액|증여금액|증여액|증여재산|증여|시가|평가액"
PRIOR_LABEL = r"사전증여|이전 증여|이전에 받은 증여|전에 받은 증여|10년 내 증여|10년 이내 증여|과거 증여"
DEBT_LABEL = r"채무|대출|담보대출|전세보증금|임대보증금|보증금"
MINOR = re.compile(r"미성년|초등학생|중학생|고등학생|유치원|아기|갓난|(?<!\d)(?:[0-9]|1[0-8])\s*살|(?<!\d)(?:[0-9]|1[0-8])\s*세(?![금액율])")
ADULT = re.compile(r"성년|성인|대학생|직장인|사회초년생|(?<!\d)(?:19|[2-9]\d)\s*살|(?<!\d)(?:19|[2-9]\d)\s*세(?![금액율])|결혼|혼인")
MARRIAGE = re.compile(r"결혼|혼인|출산|출생|아이를 낳|아기를 낳|입양")
WINDOW = re.compile(r"2\s*년\s*(?:이내|안)|(?:결혼|혼인|출산)\s*(?:을\s*)?(?:예정|앞두|준비)|"
                    r"(?:결혼|혼인|출산|태어난|낳은)\s*(?:한\s*)?지\s*(?:1\s*년|[1-9]\s*개월|\d{1,2}\s*개월)")
CHILD_GIVES = re.compile(r"(?:아들|딸|(?<!손)자녀|자식)(?:에게서|한테서|으로부터|로부터|이|가|께서)")
DECEASED_PARENT = re.compile(r"(?:아버지|어머니|아빠|엄마|부모|아들|딸|자녀)(?:가|는|께서)?\s*(?:돌아가|사망|별세)")
PRIOR_MENTION = re.compile(r"(?:이전|전에|예전에|작년|재작년|\d+\s*년\s*전)[^.?!\n]{0,20}(?:증여|받았|받은)")
LATE = re.compile(r"신고\s*(?:를\s*)?(?:안|못|않|늦|기한\s*(?:이\s*)?지)|기한\s*후\s*신고|무신고")
UNSUPPORTED = re.compile(
    r"상속|창업자금|가업승계|영농|비거주|해외|국외|명의신탁|차명|증여\s*추정|저가|고가\s*양수|특수관계법인|"
    r"일감|합산배제|비상장|자금출처|증여의제|사업기회|여러\s*명|각각|공동")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def _verb_amount(text):
    """'3억을 증여받으면', '아들에게 5억 주면'."""
    values = {parse_money(m.group(1)) for m in re.finditer(r"(" + _MONEY.pattern + r")\s*" + GIVE, text)}
    if len(values) > 1:
        raise ValueError("conflicting_amounts")
    return values.pop() if values else None


def _relation(text):
    """(relation, generation_skipping) from who gives and who receives; None when unclear."""
    found = {name for name, pattern in (("spouse", SPOUSE), ("parent", PARENT), ("grandparent", GRANDPARENT),
                                         ("child", CHILD), ("grandchild", GRANDCHILD), ("relative", RELATIVE),
                                         ("stranger", STRANGER)) if re.search(pattern, text)}
    if found <= {"spouse"} and found:
        return "배우자", False
    if "grandparent" in found or "grandchild" in found:
        return ("직계존비속", True) if not found & {"spouse", "relative", "stranger"} else (None, False)
    if found & {"parent", "child"} and not found & {"spouse", "relative", "stranger"}:
        return "직계존비속", False
    if found == {"relative"}:
        return "기타친족", False
    if found == {"stranger"}:
        return "기타", False
    return None, False


def stated_gift_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    try:
        amount = next((v for v in (stated_amount(AMOUNT_LABEL, t) or _verb_amount(t) for t in reversed(texts))
                       if v is not None), None)
        prior = next((v for v in (stated_amount(PRIOR_LABEL, t) for t in reversed(texts)) if v is not None), None)
        debts = next((v for v in (stated_amount(DEBT_LABEL, t) for t in reversed(texts)) if v is not None), None)
    except ValueError:
        return None
    if amount is None:
        return None
    relation, skipping = _relation(text)
    missing = []
    if relation is None:
        missing.append("증여자와 받는 사람의 관계(배우자, 부모·조부모→자녀·손자녀, 그 밖의 친족, 남)")
    # A parent or grandparent gives unless the child is named as the giver.
    ascendant = relation == "직계존비속" and not CHILD_GIVES.search(text)
    minor = True if MINOR.search(text) else False if ADULT.search(text) else None
    if ascendant and minor is None:
        missing.append("받는 사람이 미성년자인지(부모·조부모에게 받으면 공제가 5천만원 또는 2천만원)")
    marriage = ascendant and bool(MARRIAGE.search(text))
    if marriage and not WINDOW.search(text):
        missing.append("혼인신고일 전후 2년 또는 자녀 출생일부터 2년 이내에 받는 증여인지(혼인·출산 공제 1억원)")
    if PRIOR_MENTION.search(text) and prior is None:
        missing.append("10년 안에 같은 사람(부모는 두 분을 한 사람으로 봄)에게 받은 이전 증여액")
    if missing:
        return MissingInputs(missing)
    if debts is not None and debts > amount:
        return None
    if skipping and DECEASED_PARENT.search(text):
        skipping = False

    skipping = skipping and ascendant
    params = {"gift_amount": amount, "relation": relation, "is_minor": bool(minor and ascendant),
              "prior_gifts_10y": prior or 0, "debts": debts or 0, "prior_gift_tax": 0, "prior_gift_taxable": 0,
              "deduction_used_10y": 0, "marriage_birth": marriage, "marriage_birth_used": 0,
              "generation_skipping": skipping, "filed_on_time": not LATE.search(text)}
    assumptions = []
    if prior:
        assumptions.append(f"이전 증여 {prior:,}원은 10년 안에 같은 사람에게 받은 것으로 보고 합산했습니다.")
    else:
        assumptions.append("10년 안에 같은 사람에게 받은 다른 증여는 없다고 보았습니다.")
    if relation != "기타":
        assumptions.append("같은 관계(예: 부모·조부모)에게 받은 다른 증여로 이미 증여재산공제를 쓰지 않았다고 보았습니다. "
                           "썼다면 공제가 줄어 세금이 늘어납니다.")
    if marriage:
        assumptions.append("혼인·출산 증여재산공제를 이전에 받은 적이 없다고 보았습니다(평생 1억원 한도).")
    if skipping:
        assumptions.append("조부모가 손자녀에게 주는 증여로, 손자녀의 부모가 살아 있어 세대생략 할증(30%)을 적용했습니다.")
    if debts:
        assumptions.append(f"받는 사람이 채무 {debts:,}원을 인수하는 부담부증여로 보았습니다.")
    assumptions.append(f"증여재산가액은 말씀하신 {amount:,}원(시가)으로 보았습니다. 부동산·주식은 평가 방법에 따라 달라질 수 있습니다.")
    return StatedInputs(params, assumptions)

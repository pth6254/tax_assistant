"""Read a VAT question into calculator inputs plus stated assumptions.

Whether the business is 일반과세자 or 간이과세자 decides the whole formula, and a 간이과세자's industry
decides its rate, so both are asked when missing. Sales and purchases are read as one filing period
(일반 6개월, 간이 1년): 일반과세자 amounts as 공급가액 without VAT, 간이과세자 amounts as 공급대가 with
VAT. Purchases are taken as fully deductible. What only lowers the tax when the user has it (카드매출,
예정고지세액, 전자신고) defaults to none and is listed with the result. Anything the calculator does not
model (의제매입, 공통매입 안분, 대손, 간주임대료 …) returns None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.financial_inputs import ambiguous_thousands, stated_amount

SALES = r"과세매출|매출액|매출|공급가액|공급대가|수입금액"
PURCHASES = r"매입액|매입|비용"
CARD = r"카드매출|카드 매출|신용카드 매출|신용카드매출|현금영수증 매출|카드·현금영수증 매출"
EXEMPT = r"면세매출|면세 매출"
ZERO = r"영세율 매출|영세율매출|수출"
PREPAID = r"예정고지세액|예정고지|예정부과세액|예정부과|예정신고 미환급세액"
SIMPLE = re.compile(r"간이\s*과세|간이사업자|간이(?=[이는가로])")
GENERAL = re.compile(r"일반\s*과세|일반사업자|법인")
CORPORATE = re.compile(r"법인")
E_FILING = re.compile(r"전자신고|홈택스로\s*신고")
INDUSTRY = [
    ("음식점업", r"음식|식당|카페|커피|치킨|분식|주점|술집|베이커리|빵집"),
    ("소매업", r"소매|편의점|마트|가게|잡화|옷가게|의류|화장품|꽃집|쇼핑몰|온라인\s*판매"),
    ("숙박업", r"숙박|펜션|모텔|게스트하우스|민박"),
    ("제조업", r"제조|공장|공방"),
    ("농업·임업·어업", r"농업|임업|어업|농사|양식"),
    ("건설업", r"건설|인테리어|공사"),
    ("운수·창고업", r"운수|화물|택배|운송|택시|창고"),
    ("정보통신업", r"정보통신|소프트웨어|앱\s*개발|출판|방송"),
    ("부동산임대업", r"부동산\s*임대|임대업|상가\s*임대|건물\s*임대"),
    ("서비스업", r"서비스|미용|헤어|네일|학원|세탁|수리|컨설팅|디자인|사진|광고"),
]
UNSUPPORTED = re.compile(r"의제매입|면세\s*농산물|공통매입|안분|대손|간주임대료|보증금|겸업|겸영|재고매입|"
                         r"폐업|사업\s*양도|가산세|수정신고|기한\s*후")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def stated_vat_inputs(query, history=None):
    """StatedInputs, MissingInputs (ask the user), or None (not a case this reader handles)."""
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    latest = lambda label: next((v for v in (stated_amount(label, t) for t in reversed(texts)) if v is not None), None)
    try:
        card, exempt, zero = latest(CARD), latest(EXEMPT), latest(ZERO)
        sales = next((v for v in (stated_amount(SALES, re.sub(CARD + "|" + EXEMPT + "|" + ZERO, "", t))
                                  for t in reversed(texts)) if v is not None), None)
        purchases, prepaid = latest(PURCHASES), latest(PREPAID)
    except ValueError:
        return None
    if sales is None:
        return None
    simple, general = bool(SIMPLE.search(text)), bool(GENERAL.search(text))
    industries = [name for name, pattern in INDUSTRY if re.search(pattern, text)]
    missing = []
    if simple == general:
        missing.append("일반과세자인지 간이과세자인지")
    elif simple and len(industries) != 1:
        missing.append("업종(간이과세자는 업종별 부가가치율 15~40%로 계산)")
    if missing:
        return MissingInputs(missing)
    if simple and (exempt or zero):
        return None
    if (exempt or 0) + (zero or 0) > sales or (card or 0) > sales * 11 // 10:
        return None

    params = {"sales": sales, "purchases": purchases or 0, "exempt_sales": exempt or 0, "is_simplified": simple,
              "business_type": industries[0] if simple else "소매업", "zero_rated_sales": zero or 0,
              "common_purchases": 0, "non_deductible_purchases": 0, "deemed_purchases": 0, "card_sales": card or 0,
              "card_credit_eligible": not CORPORATE.search(text), "card_credit_used": 0,
              "e_filing": bool(E_FILING.search(text)), "prepaid_tax": prepaid or 0}
    if simple:
        assumptions = [f"간이과세자 {industries[0]}의 1년(1.1.~12.31.) 공급대가(부가가치세 포함)로 보았습니다."]
    else:
        assumptions = ["일반과세자의 한 과세기간(6개월) 금액이며 매출·매입은 부가가치세를 뺀 공급가액으로 보았습니다."]
    if purchases:
        assumptions.append("매입은 모두 세금계산서·사업용 카드 등으로 받아 공제되는 금액으로 보았습니다"
                           "(접대비·비영업용 승용차 등 불공제 매입은 빼고 입력해야 합니다).")
    else:
        assumptions.append("공제받을 매입은 없다고 보았습니다.")
    if card is None and not CORPORATE.search(text):
        assumptions.append("신용카드·현금영수증 매출은 없다고 보아 발행세액공제(1.3%)를 반영하지 않았습니다.")
    if prepaid is None:
        assumptions.append("예정고지(부과)세액은 없다고 보았습니다. 이미 고지받아 낸 세액이 있으면 그만큼 빠집니다.")
    return StatedInputs(params, assumptions)

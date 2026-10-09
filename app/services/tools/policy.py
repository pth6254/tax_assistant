"""Execution eligibility and input provenance, independent of model proposals."""
import re
from decimal import Decimal
from pydantic import ValidationError
from app.services.law.reference_parser import extract_law_reference, parse_law_reference
from app.services.tools.registry import TOOL_SCHEMAS

DOCUMENT_INTENT = re.compile(
    r"(?<![가-힣])(?:내|제|저의|우리)\s*(?:문서|계약서|서류|자료|파일)|"
    r"(?:업로드|첨부)(?:한|된|해\s*둔|했던)\s*(?:문서|계약서|서류|자료|파일|PDF)|"
    r"(?:PDF|pdf|문서|계약서|파일).{0,30}(?:찾아\s*줘|찾아주세요|검색해\s*줘|검색해\s*주세요|요약해\s*줘|요약해\s*주세요|내용\s*보여)"
)


def has_lookup_intent(query):
    """A reference in an explanation is not a request to execute a lookup."""
    try:
        if parse_law_reference(query.strip().rstrip("?.!")).article is not None:
            return True
    except ValueError:
        pass
    reference = extract_law_reference(query)
    if reference and re.search(r"보여\s*(?:줘|주세요)|조회\s*(?:해\s*줘|해\s*주세요|해주세요)", query):
        return True
    if not reference and re.search(r"관련|근거|어떤|찾", query):
        return False  # Discovering the applicable article is ordinary retrieval.
    return bool(re.search(r"(?:원문|조문)(?:을|를)?\s*(?:보여|조회(?:해\s*(?:줘|주세요)|해주세요|[?.!]*$)|그대로|[?.!]*$)", query))
CALC_TAX = {
    "income_tax": r"소득|수입", "capital_gains": r"양도|매도", "inheritance": r"상속|유산",
    "gift": r"증여", "vat": r"부가세|부가가치세|매출|매입|VAT", "penalty_tax": r"가산세",
    "financial_income_tax": r"금융소득|이자|배당",
}
FINANCIAL_INCOME = re.compile(r"금융\s*(?:소득|종합)|이자\s*소득|배당\s*소득")


def financial_income_scope(query, history=None):
    if FINANCIAL_INCOME.search(query):
        return True
    # Another tax named in this turn ends a financial-income follow-up; the financial
    # pattern itself must not, or "이자 1억이면?" would leave the financial scope.
    if any(re.search(pattern, query, re.I) for tool, pattern in CALC_TAX.items() if tool != "financial_income_tax"):
        return False
    previous = next((m.get("content", "") for m in reversed(history or []) if m.get("role") == "user"), "")
    return bool(FINANCIAL_INCOME.search(previous))


ALIASES = {
    "income": "연소득|소득|총수입|수입", "expense": "필요경비|경비", "personal_deduction_count": "공제인원|공제 인원|기본공제 인원",
    "other_deductions": "기타공제|기타 공제", "transfer_price": "양도가액|양도 가액|매도가|매도금액",
    "acquisition_price": "취득가액|취득 가액|매수가", "expenses": "필요경비|경비",
    "holding_years": "보유기간|보유 기간", "estate_value": "상속재산|상속 재산|유산",
    "debts": "채무|부채", "spouse_inheritance": "배우자 상속액|배우자 상속",
    "children_count": "자녀 수|자녀수|자녀", "gift_amount": "증여액|증여금액|증여 금액|증여",
    "prior_gifts_10y": "사전증여|사전 증여|10년 이내 증여", "sales": "매출액|매출",
    "purchases": "매입액|매입", "exempt_sales": "면세매출|면세 매출",
    "unpaid_tax": "미납세액|미납 세액|미납세금", "days_late": "지연일수|지연 일수",
    "interest_income": "이자소득|이자 소득|예금이자|예금 이자|이자",
    "non_business_interest": "비영업대금의 이익|비영업대금이익|비영업대금",
    "dividend_gross_up": "배당가산 대상 배당|내국법인 배당|배당소득|배당",
    "dividend_other": "배당가산 비대상 배당|가산 비대상 배당|외국법인 배당",
    "other_income": "다른 종합소득금액|다른 종합소득|다른 소득금액|다른 소득|사업소득금액|근로소득금액",
    "income_deductions": "종합소득공제|소득공제",
}
NUMBER = r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>억원?|천만원?|백만원?|만원?|천원|원|명|년|일)?"
UNITS = {"억": 10**8, "억원": 10**8, "천만": 10**7, "천만원": 10**7,
         "백만": 10**6, "백만원": 10**6, "만": 10**4, "만원": 10**4, "천원": 1000}
BOOL_TEXT = {
    "is_simplified": {True: "간이과세", False: "일반과세"},
    "is_one_home": {True: "1세대 1주택", False: "다주택"},
    "is_minor": {True: "미성년", False: "성년"},
    "is_negligent": {True: "부정행위 있음", False: "부정행위 없음"},
    # "원천징수" alone is also inside "원천징수되지 않은"; the two forms must not overlap.
    "withheld": {True: "원천징수된", False: "원천징수되지"},
}


def user_inputs(query, history):
    return [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-4:] + [query]


def input_proof(field, value, texts):
    """Latest explicitly labelled value wins; equal numbers in another field do not."""
    if isinstance(value, bool):
        options = BOOL_TEXT.get(field, {})
        for text in reversed(texts):
            explicit = list(re.finditer(re.escape(field) + r"\s*[:=]\s*(true|false)\b", text, re.I))
            if explicit:
                hit = explicit[-1]
                return hit.group() if (hit[1].lower() == "true") == value else None
            hits = [(m.start(), v, m.group()) for v, word in options.items()
                    for m in re.finditer(r"(?<![가-힣])" + re.escape(word), text)]
            if hits:
                _, observed, quote = max(hits)
                return quote if observed == value else None
        return None
    if isinstance(value, (int, float)):
        aliases = ALIASES.get(field, re.escape(field))
        pattern = re.compile(r"(?<![A-Za-z_가-힣])(?:" + re.escape(field) + "|" + aliases + r")[\s:=은는이가]*" + NUMBER)
        for text in reversed(texts):
            hits = list(pattern.finditer(text))
            if field == "sales":
                hits = [h for h in hits if not re.search(r"면세\s*$", text[:h.start()])]
            if hits:
                hit = hits[-1]
                if re.match(r"\s*\d", text[hit.end():]):
                    return None  # Do not accept only the first part of 5억 5000만원.
                unit = hit['unit']
                expected_unit = {"holding_years": "년", "days_late": "일", "children_count": "명",
                                 "personal_deduction_count": "명"}.get(field)
                if expected_unit and unit not in {None, expected_unit}:
                    return None
                if not expected_unit and (unit in {"명", "년", "일"} or unit is None and Decimal(hit['number'].replace(',', '')) != 0):
                    return None
                observed = Decimal(hit['number'].replace(',', '')) * UNITS.get(hit['unit'], 1)
                return hit.group() if observed == Decimal(str(value)) else None
        return None
    for text in reversed(texts):
        if field == "relation" and value == "기타":
            if re.search(r"(?:relation|관계)[\s:=은는이가]*기타", text):
                return "관계 기타"
            continue
        if str(value) and re.search(r"(?<![가-힣])" + re.escape(str(value)), text):
            return str(value)
    return None


def check_proposal(tool, params, query, history, *, calculation_intent=False):
    """Return (allowed, reason, input_proofs). Never execute on a guess."""
    texts = user_inputs(query, history)
    if tool not in TOOL_SCHEMAS:
        return False, "unsupported_tool", {}
    if tool == "document_search":
        return bool(DOCUMENT_INTENT.search(query)), "document_request_required", {}
    if tool == "law_lookup":
        if not has_lookup_intent(query):
            return False, "explicit_lookup_request_required", {}
        try:
            selected = parse_law_reference(params.get("article_no", ""))
        except ValueError:
            return False, "invalid_reference", {}
        current = extract_law_reference(query)
        if not current or current.article is None:
            return False, "explicit_reference_required", {}
        if current.article_no != selected.article_no or any(
            getattr(current, k) != getattr(selected, k) for k in ("paragraph", "item", "item_branch", "subitem")
        ):
            return False, "reference_not_from_user", {}
        names = [extract_law_reference(t) for t in texts]
        names = [r.law_name for r in names if r and r.law_name]
        expected = current.law_name or (names[-1] if names else "")
        ok = bool(expected) and re.sub(r"\s", "", expected) == re.sub(r"\s", "", params.get("law_name", ""))
        return ok, "law_not_from_user", {}
    scope_text = query if any(re.search(p, query, re.I) for p in CALC_TAX.values()) else "\n".join(texts)
    if tool == "income_tax" and financial_income_scope(query, history):
        return False, "unsupported_financial_income_calculation", {}
    if re.search(r"법인세.{0,10}(?:계산|얼마)|법인소득", scope_text):
        return False, "unsupported_calculation", {}
    if not calculation_intent or not re.search(CALC_TAX[tool], scope_text, re.I):
        return False, "calculation_request_mismatch", {}
    try:
        request = TOOL_SCHEMAS[tool].model_validate(params, strict=True, extra="forbid")
    except ValidationError as exc:
        return False, "missing_input" if any(e['type'] == 'missing' for e in exc.errors()) else "invalid_input", {}
    # Defaults are financially material too: zero, false and eligibility are not assumed.
    proofs = {key: input_proof(key, value, texts) for key, value in request.model_dump().items()}
    missing = [key for key, proof in proofs.items() if proof is None]
    return not missing, "unconfirmed_inputs:" + ",".join(missing), proofs

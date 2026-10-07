"""Routing must not depend on incidental words (metamorphic contracts, no model calls).

Each base question is an ordinary analysis request. Rewording that does not change
what the user asks for must not change which pipeline handles it. Known defects
are recorded as strict xfail so that a fix is noticed and the marker removed.
"""
import pytest

from app.services.law.history_context import route as history_route
from app.services.tools.planner import has_calculation_intent
from app.services.tools.policy import DOCUMENT_INTENT, has_lookup_intent


def signature(query):
    return {
        "archive": history_route(query, []) is not None,
        "calculation": has_calculation_intent(query),
        "lookup": has_lookup_intent(query),
        "document": bool(DOCUMENT_INTENT.search(query)),
    }


ANALYSIS = {"archive": False, "calculation": False, "lookup": False, "document": False}

BASES = {
    "gift": "A는 성년 거주자이고 어머니에게서 현금 3천만원을 증여받았습니다. 증여재산 공제를 설명해 주세요.",
    "interest": "A는 거주자이고 국내 예금이자 180만원을 받았으며 원천징수되었습니다. 종합소득과세표준에 합산하는지 판단해 주세요.",
    "capital_gains": "A는 등기된 국내 토지를 3년 6개월 보유한 뒤 양도했습니다. 장기보유 특별공제 기준을 설명해 주세요.",
    "vat": "개인사업자 A가 업무용 노트북을 구입했습니다. 부가가치세 매입세액 공제 요건과 예외를 설명해 주세요.",
    "corporate": "B회사가 거래처 접대비를 지출했습니다. 법인세 손금 인정 요건을 검토해 주세요.",
    "inheritance": "A의 아버지가 사망해 주택을 상속받았습니다. 상속세 과세가액에 포함되는 재산을 설명해 주세요.",
}

# Rewording that keeps the request an explanation of current law.
NEUTRAL = {
    "generic_law_word": lambda q: "한국 세법상 " + q,
    "calculation_word_in_topic": lambda q: q + " 과세표준 계산 구조도 함께 설명해 주세요.",
    "documents_word": lambda q: q + " 신고할 때 필요한 서류도 알려주세요.",
    "bare_current_year": lambda q: "2026년에 " + q,
}

# An event date together with a statute name is still an analysis request, but the
# archive route takes it before question planning. Changing that order is a
# separate design step (see docs/ai/HANDOFF.md), so the gap is pinned here.
EVENT_DATE_WITH_LAW = {
    "event_date_and_law_name": lambda q: "2026년 6월 1일 거래입니다. 소득세법 기준으로 " + q,
}


@pytest.mark.parametrize("base", BASES)
def test_base_questions_are_analysis(base):
    assert signature(BASES[base]) == ANALYSIS


@pytest.mark.parametrize("variant", NEUTRAL)
@pytest.mark.parametrize("base", BASES)
def test_neutral_rewording_keeps_route(base, variant):
    assert signature(NEUTRAL[variant](BASES[base])) == signature(BASES[base])


@pytest.mark.xfail(strict=True, reason="날짜+법령명 분석 질문이 질문 계획 전에 과거 법령 경로로 분기됨")
@pytest.mark.parametrize("variant", EVENT_DATE_WITH_LAW)
@pytest.mark.parametrize("base", BASES)
def test_event_date_with_law_name_keeps_route(base, variant):
    assert signature(EVENT_DATE_WITH_LAW[variant](BASES[base])) == signature(BASES[base])


@pytest.mark.parametrize("query, key", [
    ("2024-01-01 기준 소득세법 제14조 원문", "archive"),
    ("구법 기준 소득세법 제14조를 보여줘", "archive"),
    ("법령버전 12 소득세법 제14조", "archive"),
    ("소득세법 제14조 원문 보여줘", "lookup"),
    ("양도소득세 계산해줘", "calculation"),
    ("증여세는 얼마야?", "calculation"),
    ("내 계약서에서 보증금 조항 찾아줘", "document"),
])
def test_explicit_signals_still_route(query, key):
    assert signature(query)[key]

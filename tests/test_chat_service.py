"""
test_chat_service.py — chat_service 단위 테스트 (DB·Ollama 의존 없음)
"""
from app.services.calculator.engine import CalcRun
from app.services.chat_service import (
    _build_final_messages,
    _calc_meta,
    _match_laws_by_keyword,
    _COMBINED_PROMPT,
)


# ── _match_laws_by_keyword — 키워드 매핑 ─────────────────────────

def test_match_income_tax():
    assert _match_laws_by_keyword("소득세 신고 방법이 궁금해요") == ["소득세법"]


def test_match_vat():
    assert _match_laws_by_keyword("부가세 환급 받으려면 어떻게 하나요") == ["부가가치세법"]


def test_match_inheritance():
    assert _match_laws_by_keyword("상속세 신고 기한이 얼마나 되나요") == ["상속세 및 증여세법"]


def test_match_none_returns_empty():
    assert _match_laws_by_keyword("오늘 날씨가 정말 좋네요") == []


def test_match_overlap_longer_keyword_wins():
    """겹치는 키워드는 더 긴(구체적인) 쪽만 채택 — '지방소득세'가 '소득세'를 이겨야 한다."""
    assert _match_laws_by_keyword("지방소득세는 어떻게 계산하나요") == ["지방세법"]


def test_match_overlap_compound_keyword_wins():
    """'지방세 체납'은 국세징수법('체납')이 아닌 지방세징수법으로 매칭되어야 한다."""
    assert _match_laws_by_keyword("지방세 체납하면 어떻게 되나요") == ["지방세징수법"]


def test_match_generic_deduction_word_not_special_law():
    """'공제'류 일반 용어만으로 조세특례제한법에 매칭되면 안 된다 (과거 버그)."""
    assert _match_laws_by_keyword("종합소득세 기본공제 금액은 얼마인가요?") == ["소득세법"]


# ── _build_final_messages ────────────────────────────────────────

def test_build_final_messages_first_is_system_prompt():
    msgs = _build_final_messages("질문", "법령자료", "웹결과", [])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == _COMBINED_PROMPT


def test_build_final_messages_last_is_user_with_query():
    msgs = _build_final_messages("소득세 신고 방법", "법령자료", "웹결과", [])
    assert msgs[-1]["role"] == "user"
    assert "소득세 신고 방법" in msgs[-1]["content"]


def test_build_final_messages_contains_rag_context():
    msgs = _build_final_messages("질문", "제55조 [세율] 조문 내용", "웹결과", [])
    assert "제55조 [세율] 조문 내용" in msgs[-1]["content"]


def test_build_final_messages_contains_web_results():
    msgs = _build_final_messages("질문", "법령자료", "Tavily 웹 검색 결과", [])
    assert "Tavily 웹 검색 결과" in msgs[-1]["content"]


def test_build_final_messages_skips_web_placeholder():
    """웹검색이 생략된 경우 '웹 검색 생략' 플레이스홀더는 프롬프트에 넣지 않는다."""
    msgs = _build_final_messages("질문", "법령자료", "웹 검색 생략", [])
    assert "웹 검색 생략" not in msgs[-1]["content"]


def test_build_final_messages_includes_calc_context():
    calc = CalcRun(context="세목: 소득세\n- 결정세액: 5,895,000원", tool="income_tax", params={"income": 50000000})
    msgs = _build_final_messages("질문", "법령자료", "웹 검색 생략", [], calc)
    assert "결정세액: 5,895,000원" in msgs[-1]["content"]
    assert "세금 계산기 결과" in msgs[-1]["content"]


def test_build_final_messages_history_inserted_between():
    history = [
        {"role": "user",      "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    msgs = _build_final_messages("새 질문", "법령자료", "웹결과", history)
    contents = [m["content"] for m in msgs]
    assert "이전 질문" in contents
    assert "이전 답변" in contents
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"


def test_build_final_messages_empty_history_two_messages():
    msgs = _build_final_messages("질문", "법령자료", "웹 검색 생략", [])
    assert len(msgs) == 2  # system + user


# ── _calc_meta ───────────────────────────────────────────────────

def test_calc_meta_none_when_no_calc():
    assert _calc_meta(None) is None


def test_calc_meta_returns_tool_and_params():
    calc = CalcRun(context="...", tool="gift", params={"gift_amount": 300000000})
    assert _calc_meta(calc) == {"tool": "gift", "params": {"gift_amount": 300000000}}

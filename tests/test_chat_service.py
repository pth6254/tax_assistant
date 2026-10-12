"""
test_chat_service.py — chat_service 단위 테스트 (DB·Ollama 의존 없음)
"""
from app.services.calculator.engine import CalcRun
from app.services.ai_pipeline import to_provider_messages
from app.services.chat_service import _calc_meta, _match_laws_by_keyword
from evaluation.fixed_context_answer import _COMBINED_PROMPT, FIXED_CONTEXT_TEMPLATE, prompt_values


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


def test_polite_ending_does_not_select_liquor_tax():
    assert _match_laws_by_keyword("법인세 처리 방법을 설명해 주세요.") == ["법인세법"]
    assert _match_laws_by_keyword("주세법의 과세 대상을 설명해 주세요.") == ["주세법"]


# ── 평가용 고정 근거 답변 프롬프트(answer_fixed_context) ─────────

def test_fixed_context_prompt_puts_the_rules_first_and_the_question_last():
    msgs = to_provider_messages(FIXED_CONTEXT_TEMPLATE.invoke(prompt_values("소득세 신고 방법", "제55조 [세율] 조문 내용")))
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == _COMBINED_PROMPT
    assert "제55조 [세율] 조문 내용" in msgs[-1]["content"] and "소득세 신고 방법" in msgs[-1]["content"]


# ── _calc_meta ───────────────────────────────────────────────────

def test_calc_meta_none_when_no_calc():
    assert _calc_meta(None) is None


def test_calc_meta_returns_tool_and_params():
    calc = CalcRun(context="...", tool="gift", params={"gift_amount": 300000000})
    assert _calc_meta(calc) == {"tool": "gift", "params": {"gift_amount": 300000000}}

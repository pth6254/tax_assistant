"""
test_chat_service.py — chat_service 단위 테스트 (DB·Ollama 의존 없음)
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.calculator.engine import CalcRun
from app.services.ai_pipeline import to_provider_messages
from app.services.chat_service import (
    _append_source_list_if_missing,
    _FINAL_PROMPT_TEMPLATE,
    _final_prompt_values,
    _calc_meta,
    _match_laws_by_keyword,
    _COMBINED_PROMPT,
)

_CONTEXT = (
    "[출처: 소득세법 | 소득세법 | 📌 법률 (law)]\n"
    "제55조 [세율]\n소득세는 다음 각 호의 세율을 적용한다..."
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


# ── 실제 최종 답변 템플릿 ────────────────────────────────────────

@pytest.fixture
def render_final_messages():
    def render(query, context, web_results, history, calc_run=None):
        values = _final_prompt_values(query, context, web_results, history, calc_run)
        return to_provider_messages(_FINAL_PROMPT_TEMPLATE.invoke(values))
    return render

def test_final_prompt_first_is_system_prompt(render_final_messages):
    msgs = render_final_messages("질문", "법령자료", "웹결과", [])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == _COMBINED_PROMPT


def test_final_prompt_last_is_user_with_query(render_final_messages):
    msgs = render_final_messages("소득세 신고 방법", "법령자료", "웹결과", [])
    assert msgs[-1]["role"] == "user"
    assert "소득세 신고 방법" in msgs[-1]["content"]


def test_final_prompt_contains_rag_context(render_final_messages):
    msgs = render_final_messages("질문", "제55조 [세율] 조문 내용", "웹결과", [])
    assert "제55조 [세율] 조문 내용" in msgs[-1]["content"]


def test_final_prompt_contains_web_results(render_final_messages):
    msgs = render_final_messages("질문", "법령자료", "Tavily 웹 검색 결과", [])
    assert "Tavily 웹 검색 결과" in msgs[-1]["content"]


def test_final_prompt_skips_web_placeholder(render_final_messages):
    """웹검색이 생략된 경우 '웹 검색 생략' 플레이스홀더는 프롬프트에 넣지 않는다."""
    msgs = render_final_messages("질문", "법령자료", "웹 검색 생략", [])
    assert "웹 검색 생략" not in msgs[-1]["content"]


def test_final_prompt_includes_calc_context(render_final_messages):
    calc = CalcRun(context="세목: 소득세\n- 결정세액: 5,895,000원", tool="income_tax", params={"income": 50000000})
    msgs = render_final_messages("질문", "법령자료", "웹 검색 생략", [], calc)
    assert "결정세액: 5,895,000원" in msgs[-1]["content"]
    assert "세금 계산기 결과" in msgs[-1]["content"]


def test_final_prompt_history_inserted_between(render_final_messages):
    history = [
        {"role": "user",      "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    msgs = render_final_messages("새 질문", "법령자료", "웹결과", history)
    contents = [m["content"] for m in msgs]
    assert "이전 질문" in contents
    assert "이전 답변" in contents
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"


def test_final_prompt_empty_history_two_messages(render_final_messages):
    msgs = render_final_messages("질문", "법령자료", "웹 검색 생략", [])
    assert len(msgs) == 2  # system + user


# ── _calc_meta ───────────────────────────────────────────────────

def test_calc_meta_none_when_no_calc():
    assert _calc_meta(None) is None


def test_calc_meta_returns_tool_and_params():
    calc = CalcRun(context="...", tool="gift", params={"gift_amount": 300000000})
    assert _calc_meta(calc) == {"tool": "gift", "params": {"gift_amount": 300000000}}


# ── _append_source_list_if_missing — 인용 누락 보정 (structured output) ──

@pytest.mark.asyncio
async def test_source_list_appended_when_answer_has_no_citation():
    """인용 없는 답변 + 검증 가능한 structured 추출 결과 → 출처 목록 섹션이 붙는다."""
    structured = AsyncMock(return_value={"citations": [
        {"label": "법률", "law_name": "소득세법", "article_no": "제55조"},
    ]})
    with patch("app.services.chat_service.call_llm_structured", structured):
        result = await _append_source_list_if_missing("세율은 6~45%입니다.", _CONTEXT)
    assert "## 📋 근거 출처 목록" in result
    assert "[법률] 소득세법 제55조" in result


@pytest.mark.asyncio
async def test_source_list_skipped_when_answer_already_cited():
    """이미 인용이 있는 답변은 보정 LLM 호출 자체가 실행되지 않는다 (지연 0)."""
    structured = AsyncMock()
    answer = "[법률] 소득세법 제55조에 따라 과세됩니다."
    with patch("app.services.chat_service.call_llm_structured", structured):
        result = await _append_source_list_if_missing(answer, _CONTEXT)
    assert result == answer
    structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_list_filters_hallucinated_citation():
    """structured 추출이 컨텍스트에 없는 조문을 반환하면 채택하지 않는다 (환각 차단)."""
    structured = AsyncMock(return_value={"citations": [
        {"label": "법률", "law_name": "부가가치세법", "article_no": "제999조"},
    ]})
    answer = "관련 규정에 따라 과세됩니다."
    with patch("app.services.chat_service.call_llm_structured", structured):
        result = await _append_source_list_if_missing(answer, _CONTEXT)
    assert result == answer


@pytest.mark.asyncio
async def test_source_list_unchanged_on_structured_call_failure():
    """보정 호출이 실패해도 원본 답변은 그대로 반환된다."""
    structured = AsyncMock(side_effect=Exception("ollama down"))
    answer = "세율은 6~45%입니다."
    with patch("app.services.chat_service.call_llm_structured", structured):
        result = await _append_source_list_if_missing(answer, _CONTEXT)
    assert result == answer


@pytest.mark.asyncio
async def test_source_list_skipped_when_no_law_context():
    """검색된 법령 자료가 없으면(잡담 등) 보정을 시도하지 않는다."""
    structured = AsyncMock()
    with patch("app.services.chat_service.call_llm_structured", structured):
        result = await _append_source_list_if_missing("안녕하세요!", "관련 문서를 찾지 못했습니다.")
    assert result == "안녕하세요!"
    structured.assert_not_awaited()

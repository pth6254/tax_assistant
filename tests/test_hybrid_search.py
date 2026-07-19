"""
test_hybrid_search.py — hybrid_search_service 단위 테스트 (DB·Ollama 의존 없음)
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.law import HybridSearchResult, LawArticleDetail
from app.services.search.hybrid_search_service import (
    _lookup_referenced_article,
    _prepend_direct_hit,
    _search_documents,
    format_hybrid_context,
    hybrid_search,
)


def _make_result(**kwargs) -> HybridSearchResult:
    defaults = dict(
        content="제1조 [목적]\n조문 내용",
        source="소득세법",
        law_name="소득세법",
        category="법률",
        source_type="law",
        similarity_score=0.85,
        priority=0,
    )
    defaults.update(kwargs)
    return HybridSearchResult(**defaults)


# ── format_hybrid_context ────────────────────────────────────────

def test_format_hybrid_context_empty():
    assert format_hybrid_context([]) == "관련 문서를 찾지 못했습니다."


def test_format_hybrid_context_contains_source_and_category():
    r = _make_result(source="소득세법", law_name="소득세법", category="법률")
    text = format_hybrid_context([r])
    assert "소득세법" in text
    assert "법률" in text


def test_format_hybrid_context_multiple_results_separated():
    r1 = _make_result(content="내용1")
    r2 = _make_result(content="내용2")
    text = format_hybrid_context([r1, r2])
    assert "---" in text
    assert "내용1" in text
    assert "내용2" in text


# ── 우선순위 정렬 규칙 ────────────────────────────────────────────

def test_priority_sort_law_before_pdf():
    law = _make_result(priority=0, similarity_score=0.8, source_type="law")
    pdf = _make_result(priority=7, similarity_score=0.95, source_type="user_pdf")
    merged = sorted([pdf, law], key=lambda r: (r.priority, -r.similarity_score))
    assert merged[0].source_type == "law"


def test_priority_same_level_sorted_by_similarity():
    high = _make_result(priority=0, similarity_score=0.9)
    low  = _make_result(priority=0, similarity_score=0.6)
    merged = sorted([low, high], key=lambda r: (r.priority, -r.similarity_score))
    assert merged[0].similarity_score == 0.9


# ── _search_documents 오류 처리 ──────────────────────────────────

@pytest.mark.asyncio
async def test_search_documents_raises_without_user_id():
    with pytest.raises(ValueError, match="user_id"):
        await _search_documents([], "ALL", 5, "")


# ── 조문번호 직접 질의 fast path ──────────────────────────────────

def _make_article_detail() -> LawArticleDetail:
    return LawArticleDetail(
        law_name="부가가치세법", law_type="법률", tax_type="부가가치세법",
        article_no="제39조", article_title="공제하지 아니하는 매입세액",
        article_text="제39조(공제하지 아니하는 매입세액) ① ...",
        effective_date="", amendment_date="", source_url="",
    )


@pytest.mark.asyncio
async def test_lookup_referenced_article_with_law_name_in_query():
    with patch(
        "app.services.search.hybrid_search_service.get_law_article",
        AsyncMock(return_value=_make_article_detail()),
    ) as mock_get:
        result = await _lookup_referenced_article("부가가치세법 제39조 내용이 궁금해", "ALL")
    assert result is not None
    assert result.similarity_score == 1.0
    assert result.law_name == "부가가치세법"
    mock_get.assert_awaited_once_with("부가가치세법", "제39조")


@pytest.mark.asyncio
async def test_lookup_referenced_article_uses_law_filter_when_name_missing():
    """질문에 법령명이 없으면 세목 필터를 법령명으로 사용한다."""
    with patch(
        "app.services.search.hybrid_search_service.get_law_article",
        AsyncMock(return_value=_make_article_detail()),
    ) as mock_get:
        result = await _lookup_referenced_article("제39조 내용 알려줘", "부가가치세법")
    assert result is not None
    mock_get.assert_awaited_once_with("부가가치세법", "제39조")


@pytest.mark.asyncio
async def test_lookup_referenced_article_normalizes_spaced_number():
    """'제 39 조'처럼 공백 섞인 조문번호도 표준형으로 정규화해 조회한다."""
    with patch(
        "app.services.search.hybrid_search_service.get_law_article",
        AsyncMock(return_value=_make_article_detail()),
    ) as mock_get:
        result = await _lookup_referenced_article("부가가치세법 제 39 조 내용 알려줘", "ALL")
    assert result is not None
    mock_get.assert_awaited_once_with("부가가치세법", "제39조")


@pytest.mark.asyncio
async def test_lookup_referenced_article_distinguishes_article_branch_from_paragraph():
    """제59조의4는 조의 가지번호이고, 제9항은 조회 키에서 분리한다."""
    with patch(
        "app.services.search.hybrid_search_service.get_law_article",
        AsyncMock(return_value=_make_article_detail()),
    ) as mock_get:
        result = await _lookup_referenced_article(
            "소득세법 제59조의4 제9항 제1호 내용을 알려줘", "ALL"
        )
    assert result is not None
    mock_get.assert_awaited_once_with("소득세법", "제59조의4")


@pytest.mark.asyncio
async def test_lookup_referenced_enforcement_rule_keeps_full_law_name():
    with patch(
        "app.services.search.hybrid_search_service.get_law_article",
        AsyncMock(return_value=_make_article_detail()),
    ) as mock_get:
        result = await _lookup_referenced_article(
            "소득세법 시행규칙 제58조의2 제1항 제4호 다목을 알려줘", "ALL"
        )
    assert result is not None
    mock_get.assert_awaited_once_with("소득세법 시행규칙", "제58조의2")


@pytest.mark.asyncio
async def test_lookup_referenced_article_none_without_article_ref():
    result = await _lookup_referenced_article("매입세액 불공제 대상 알려줘", "부가가치세법")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_referenced_article_none_when_all_and_no_law_name():
    """법령명도 없고 필터도 ALL이면 조회하지 않는다."""
    result = await _lookup_referenced_article("제39조가 뭐야", "ALL")
    assert result is None


def test_prepend_direct_hit_dedupes_and_leads():
    direct = _make_result(content="제39조 [공제하지 아니하는 매입세액]\n...", law_name="부가가치세법", similarity_score=1.0)
    duplicate = _make_result(content="제39조 [공제하지 아니하는 매입세액]\n...", law_name="부가가치세법", similarity_score=0.6)
    other = _make_result(content="제38조 [공제세액]\n...", law_name="부가가치세법", similarity_score=0.7)
    merged = _prepend_direct_hit(direct, [duplicate, other])
    assert merged[0] is direct
    assert duplicate not in merged
    assert other in merged


def test_prepend_direct_hit_noop_when_none():
    results = [_make_result()]
    assert _prepend_direct_hit(None, results) == results


# ── hybrid_search (검색 함수 mock) ───────────────────────────────

@pytest.mark.asyncio
async def test_hybrid_search_empty_queries_returns_empty():
    assert await hybrid_search([]) == []


@pytest.mark.asyncio
async def test_hybrid_search_returns_empty_when_no_hits():
    with (
        patch("app.services.search.hybrid_search_service.embed_texts", AsyncMock(return_value=[[0.0] * 10])),
        patch("app.services.search.hybrid_search_service._search_law_articles", AsyncMock(return_value=[])),
        patch("app.services.search.hybrid_search_service._search_documents", AsyncMock(return_value=[])),
    ):
        results = await hybrid_search(["소득세 신고"], user_id="00000000-0000-0000-0000-000000000001")
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_filters_below_threshold():
    """유사도가 SIMILARITY_THRESHOLD 미만이면 결과에서 제외한다."""
    low = _make_result(similarity_score=0.1)
    with (
        patch("app.services.search.hybrid_search_service.embed_texts", AsyncMock(return_value=[[0.0] * 10])),
        patch("app.services.search.hybrid_search_service._search_law_articles", AsyncMock(return_value=[low])),
        patch("app.services.search.hybrid_search_service._search_documents", AsyncMock(return_value=[])),
        patch("app.services.search.hybrid_search_service.SIMILARITY_THRESHOLD", 0.4),
    ):
        results = await hybrid_search(["소득세 신고"], user_id="00000000-0000-0000-0000-000000000001")
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_returns_sorted_hits():
    law  = _make_result(priority=0, similarity_score=0.8, source_type="law")
    rule = _make_result(priority=2, similarity_score=0.9, source_type="rule", content="제2조\n...")
    with (
        patch("app.services.search.hybrid_search_service.embed_texts", AsyncMock(return_value=[[0.0] * 10])),
        patch("app.services.search.hybrid_search_service._search_law_articles", AsyncMock(return_value=[rule, law])),
        patch("app.services.search.hybrid_search_service._search_documents", AsyncMock(return_value=[])),
    ):
        results = await hybrid_search(["소득세 신고"], user_id="00000000-0000-0000-0000-000000000001")
    assert results[0].source_type == "law"  # 우선순위(법률)가 유사도보다 우선

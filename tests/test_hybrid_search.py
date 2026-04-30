"""
test_hybrid_search.py — hybrid_search_service 단위 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.law.hybrid_search_service import (
    HybridSearchResult,
    format_hybrid_context,
    _search_documents,
    hybrid_search,
)


def _make_result(**kwargs) -> HybridSearchResult:
    defaults = dict(
        content="조문 내용",
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


def test_format_hybrid_context_contains_source():
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


def test_format_hybrid_context_includes_content():
    r = _make_result(content="제1조 [목적] 이 법은...")
    text = format_hybrid_context([r])
    assert "제1조 [목적] 이 법은..." in text


# ── HybridSearchResult 우선순위 정렬 ─────────────────────────────

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


# ── hybrid_search (mock) ─────────────────────────────────────────

def _make_pool_mock(law_rows=None, doc_rows=None):
    """asyncpg pool + conn mock 생성."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[law_rows or [], doc_rows or []])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__  = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.mark.asyncio
async def test_hybrid_search_returns_empty_when_no_rows():
    pool = _make_pool_mock(law_rows=[], doc_rows=[])
    with (
        patch("app.services.law.hybrid_search_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.hybrid_search_service.embed_texts", AsyncMock(return_value=[[0.0] * 10])),
    ):
        results = await hybrid_search("소득세 신고", user_id="00000000-0000-0000-0000-000000000001")
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_filters_below_threshold():
    """유사도가 SIMILARITY_THRESHOLD 미만이면 결과에서 제외한다."""
    law_row = MagicMock()
    law_row.__getitem__ = lambda self, key: {
        "law_name": "소득세법", "law_type": "법률", "tax_type": "소득세법",
        "article_no": "제1조", "article_title": "목적",
        "article_text": "이 법은...", "source_url": "",
        "similarity_score": 0.1,  # 임계값 미만
    }[key]

    pool = _make_pool_mock(law_rows=[law_row], doc_rows=[])
    with (
        patch("app.services.law.hybrid_search_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.hybrid_search_service.embed_texts", AsyncMock(return_value=[[0.0] * 10])),
        patch("app.services.law.hybrid_search_service.SIMILARITY_THRESHOLD", 0.4),
    ):
        results = await hybrid_search("소득세 신고", user_id="00000000-0000-0000-0000-000000000001")
    assert results == []

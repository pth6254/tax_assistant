"""
test_interpretation_service.py — 법령해석례(유권해석) 수집 파이프라인 단위 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.law.interpretation_service import (
    _build_article_text,
    _extract_law_name,
    ingest_interpretations,
)


# ── _extract_law_name ─────────────────────────────────────────────

def test_extract_law_name_from_bracket():
    title = "국민권익위원회 - 부당해고기간의 임금 상당액이 「소득세법」 제20조제1항제1호의 근로소득에 해당되는지의 여부"
    assert _extract_law_name(title) == "소득세법"


def test_extract_law_name_first_bracket_only():
    title = "「조세특례제한법」 제77조와 「소득세법」 제89조의 관계"
    assert _extract_law_name(title) == "조세특례제한법"


def test_extract_law_name_no_bracket_returns_default():
    assert _extract_law_name("괄호 없는 안건명입니다") == "법령해석례"


# ── _build_article_text ───────────────────────────────────────────

def test_build_article_text_includes_all_sections():
    detail = {"question": "질의 내용", "answer": "회답 내용", "reasoning": "이유 내용"}
    text = _build_article_text(detail)
    assert "[질의요지]\n질의 내용" in text
    assert "[회답]\n회답 내용" in text
    assert "[이유]\n이유 내용" in text


def test_build_article_text_skips_empty_sections():
    detail = {"question": "질의만 있음", "answer": "", "reasoning": ""}
    text = _build_article_text(detail)
    assert text == "[질의요지]\n질의만 있음"


def test_build_article_text_all_empty_returns_empty_string():
    assert _build_article_text({}) == ""


# ── ingest_interpretations (API/DB mock) ──────────────────────────

def _make_pool_mock():
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool, conn


@pytest.mark.asyncio
async def test_ingest_interpretations_inserts_and_infers_tax_type():
    summary = {
        "case_id": "312859", "title": "임금 관련 「소득세법」 제20조 해석",
        "case_no": "10-0075", "request_agency": "", "response_agency": "법제처",
        "decision_date": "2010.04.23",
    }
    detail = {
        "case_id": "312859", "title": "임금 관련 「소득세법」 제20조 해석", "case_no": "10-0075",
        "decision_date": "20100423", "response_agency": "법제처", "request_agency": "",
        "question": "질의요지 내용", "answer": "회답 내용", "reasoning": "이유 내용",
    }
    pool, conn = _make_pool_mock()

    with (
        patch("app.services.law.interpretation_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.interpretation_service.search_expc", AsyncMock(return_value=[summary])),
        patch("app.services.law.interpretation_service.get_expc_detail", AsyncMock(return_value=detail)),
        patch(
            "app.services.law.interpretation_service._insert_article_returning_id",
            AsyncMock(return_value=42),
        ) as mock_insert,
    ):
        result = await ingest_interpretations("소득세", embed=False, max_results=10, request_delay=0)

    assert result["found"] == 1
    assert result["inserted_count"] == 1
    assert result["skipped_count"] == 0
    assert result["failed_count"] == 0

    # law_name이 안건명의 「소득세법」에서 추출되어 tax_type도 소득세법으로 추론됐는지 확인
    call_args = mock_insert.call_args
    article_arg, tax_type_arg = call_args.args[1], call_args.args[2]
    assert article_arg.law_name == "소득세법"
    assert article_arg.law_type == "법령해석례"
    assert tax_type_arg == "소득세법"


@pytest.mark.asyncio
async def test_ingest_interpretations_skips_empty_body():
    summary = {"case_id": "1", "title": "제목", "case_no": "1-1", "request_agency": "", "response_agency": "", "decision_date": ""}
    detail = {"question": "", "answer": "", "reasoning": ""}
    pool, conn = _make_pool_mock()

    with (
        patch("app.services.law.interpretation_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.interpretation_service.search_expc", AsyncMock(return_value=[summary])),
        patch("app.services.law.interpretation_service.get_expc_detail", AsyncMock(return_value=detail)),
    ):
        result = await ingest_interpretations("소득세", max_results=10, request_delay=0)

    assert result["inserted_count"] == 0
    assert result["skipped_count"] == 1


@pytest.mark.asyncio
async def test_ingest_interpretations_detail_fetch_failure_counted_as_failed():
    summary = {"case_id": "1", "title": "제목", "case_no": "1-1", "request_agency": "", "response_agency": "", "decision_date": ""}
    pool, conn = _make_pool_mock()

    with (
        patch("app.services.law.interpretation_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.interpretation_service.search_expc", AsyncMock(return_value=[summary])),
        patch("app.services.law.interpretation_service.get_expc_detail", AsyncMock(side_effect=Exception("API 오류"))),
    ):
        result = await ingest_interpretations("소득세", max_results=10, request_delay=0)

    assert result["failed_count"] == 1
    assert result["inserted_count"] == 0


@pytest.mark.asyncio
async def test_ingest_interpretations_no_results():
    pool, conn = _make_pool_mock()
    with (
        patch("app.services.law.interpretation_service.get_pool", AsyncMock(return_value=pool)),
        patch("app.services.law.interpretation_service.search_expc", AsyncMock(return_value=[])),
    ):
        result = await ingest_interpretations("존재안함키워드", max_results=10, request_delay=0)

    assert result["found"] == 0
    assert result["inserted_count"] == 0

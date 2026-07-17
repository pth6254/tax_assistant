"""
test_ingestion.py — ingestion_service 순수 함수 단위 테스트
"""
import pytest
from unittest.mock import AsyncMock

from app.services.law.ingestion_service import (
    _build_embed_text,
    _infer_tax_type,
    _make_hash,
    _supersede_stale_versions,
)
from app.services.law.parser_service import LawArticle


# ── _make_hash ───────────────────────────────────────────────────

def test_make_hash_is_deterministic():
    assert _make_hash("소득세법") == _make_hash("소득세법")


def test_make_hash_different_texts_differ():
    assert _make_hash("소득세법") != _make_hash("법인세법")


def test_make_hash_returns_hex_string():
    result = _make_hash("test")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ── _infer_tax_type ──────────────────────────────────────────────

@pytest.mark.parametrize("law_name,expected", [
    ("소득세법 시행령",         "소득세법"),
    ("법인세법",               "법인세법"),
    ("부가가치세법 시행규칙",   "부가가치세법"),
    ("상속세 및 증여세법",      "상속세 및 증여세법"),
    ("국세기본법",             "국세기본법"),
    ("조세특례제한법",          "조세특례제한법"),
    ("지방세법",               "지방세법"),
    ("국세징수법",             "국세징수법"),
    ("관세법",                 "관세법"),
])
def test_infer_tax_type_known(law_name, expected):
    assert _infer_tax_type(law_name) == expected


def test_infer_tax_type_unknown_returns_law_name():
    assert _infer_tax_type("알수없는법률") == "알수없는법률"


# ── _build_embed_text ────────────────────────────────────────────

def _make_article(text: str = "내용") -> LawArticle:
    return LawArticle(
        law_name="소득세법",
        law_type="법률",
        article_no="제1조",
        article_title="목적",
        article_text=text,
        effective_date="20260101",
        amendment_date="20251231",
    )


def test_build_embed_text_contains_law_name():
    result = _build_embed_text(_make_article(), "소득세법")
    assert "소득세법" in result


def test_build_embed_text_contains_article_no():
    result = _build_embed_text(_make_article(), "소득세법")
    assert "제1조" in result


def test_build_embed_text_contains_tax_type():
    result = _build_embed_text(_make_article(), "소득세법")
    assert "세목: 소득세법" in result


def test_build_embed_text_contains_content():
    article = _make_article("이 법은 소득세에 관한 사항을 규정한다.")
    result = _build_embed_text(article, "소득세법")
    assert "이 법은 소득세에 관한 사항을 규정한다." in result


# ── _supersede_stale_versions (법령 개정 감지) ────────────────────

@pytest.mark.asyncio
async def test_supersede_returns_count_when_rows_updated():
    """UPDATE N (N>0) 응답이면 개정 감지 — 폐기된 행 수를 반환."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 1")
    result = await _supersede_stale_versions(conn, "소득세법", "제55조", ["new_hash"])
    assert result == 1


@pytest.mark.asyncio
async def test_supersede_returns_zero_when_no_row_updated():
    """UPDATE 0이면 변경 없음(해시가 이번 수집분에 포함됨 또는 대상 행 없음)."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 0")
    result = await _supersede_stale_versions(conn, "소득세법", "제55조", ["same_hash"])
    assert result == 0


@pytest.mark.asyncio
async def test_supersede_passes_correct_sql_params():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 0")
    await _supersede_stale_versions(conn, "법인세법", "제19조", ["abc123", "def456"])
    args = conn.execute.call_args.args
    assert "법인세법" in args
    assert "제19조" in args
    assert ["abc123", "def456"] in args


@pytest.mark.asyncio
async def test_supersede_does_not_flag_other_hashes_in_same_group():
    """같은 article_no에 여러 콘텐츠가 공존하는 경우(절/관 표제 중복 이슈),
    이번 수집분 해시 집합 전체를 넘기면 그중 어느 것도 서로를 폐기시키지 않아야 한다."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="UPDATE 0")
    # 3개 콘텐츠(헤더1, 헤더2, 실제조문)가 전부 살아남는 정상 케이스를 시뮬레이션
    result = await _supersede_stale_versions(
        conn, "소득세법", "제55조", ["header1_hash", "header2_hash", "real_hash"]
    )
    assert result == 0
    args = conn.execute.call_args.args
    assert args[3] == ["header1_hash", "header2_hash", "real_hash"]

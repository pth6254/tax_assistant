"""
test_api_law.py — 법령 조문 조회 엔드포인트 테스트
"""
from unittest.mock import AsyncMock, patch

from app.schemas.law import LawArticleDetail


def _make_article() -> LawArticleDetail:
    return LawArticleDetail(
        law_name="소득세법", law_type="법률", tax_type="소득세법",
        article_no="제55조", article_title="세율",
        article_text="제55조(세율) ①거주자의 종합소득에...",
        effective_date="20260101", amendment_date="20251231",
        source_url="https://www.law.go.kr/lsInfoP.do?lsiSeq=285523",
    )


def test_lookup_without_auth_returns_401(client):
    resp = client.get("/api/law-articles/lookup", params={"law_name": "소득세법", "article_no": "제55조"})
    assert resp.status_code == 401


def test_lookup_found_returns_article(client, auth_cookie):
    with patch(
        "app.routers.law.get_law_article",
        AsyncMock(return_value=_make_article()),
    ):
        resp = client.get(
            "/api/law-articles/lookup",
            params={"law_name": "소득세법", "article_no": "제55조"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["article_no"] == "제55조"
    assert body["article_title"] == "세율"


def test_lookup_not_found_returns_404(client, auth_cookie):
    with patch(
        "app.routers.law.get_law_article",
        AsyncMock(return_value=None),
    ):
        resp = client.get(
            "/api/law-articles/lookup",
            params={"law_name": "존재안함법", "article_no": "제1조"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 404

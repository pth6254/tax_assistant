"""
test_api_upload.py — 업로드 엔드포인트 테스트
"""
import io
import pytest
from unittest.mock import AsyncMock, patch


def _make_pdf_bytes() -> bytes:
    """최소한의 유효 PDF 바이트 (헤더만)."""
    return b"%PDF-1.4 test pdf content"


# ── 인증 검사 ────────────────────────────────────────────────────

def test_upload_without_auth_returns_401(client):
    resp = client.post(
        "/api/upload",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 401


# ── 파일 형식 검사 ────────────────────────────────────────────────

def test_upload_non_pdf_returns_400(client, auth_cookie):
    resp = client.post(
        "/api/upload",
        files={"file": ("document.txt", b"text content", "text/plain")},
        cookies=auth_cookie,
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_upload_non_pdf_extension_returns_400(client, auth_cookie):
    resp = client.post(
        "/api/upload",
        files={"file": ("image.png", b"\x89PNG\r\n", "image/png")},
        cookies=auth_cookie,
    )
    assert resp.status_code == 400


# ── 정상 업로드 (서비스 mock) ─────────────────────────────────────

def test_upload_pdf_success_returns_200(client, auth_cookie):
    with patch(
        "app.services.upload_service.process_upload",
        AsyncMock(return_value={
            "status": "ok",
            "filename": "소득세법(법률).pdf",
            "law_name": "소득세법",
            "category": "법령",
            "chunks_stored": 42,
        }),
    ):
        resp = client.post(
            "/api/upload",
            files={"file": ("소득세법(법률).pdf", _make_pdf_bytes(), "application/pdf")},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["chunks_stored"] == 42

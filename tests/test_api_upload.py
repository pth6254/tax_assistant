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


def test_upload_oversized_file_returns_413(client, auth_cookie):
    from config import MAX_UPLOAD_MB
    oversized = b"A" * (MAX_UPLOAD_MB * 1024 * 1024 + 1)
    resp = client.post(
        "/api/upload",
        files={"file": ("big.pdf", oversized, "application/pdf")},
        cookies=auth_cookie,
    )
    assert resp.status_code == 413


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


# ── 문서 목록 ────────────────────────────────────────────────────

def test_list_documents_without_auth_returns_401(client):
    resp = client.get("/api/documents")
    assert resp.status_code == 401


def test_list_documents_returns_list(client, auth_cookie):
    mock_docs = [
        {
            "filename": "소득세법(법률).pdf",
            "law_name": "소득세법",
            "category": "법령",
            "chunk_count": 42,
            "uploaded_at": "2026-04-30T10:00:00+00:00",
        }
    ]
    with patch("app.services.upload_service.list_documents", AsyncMock(return_value=mock_docs)):
        resp = client.get("/api/documents", cookies=auth_cookie)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["filename"] == "소득세법(법률).pdf"


# ── 문서 삭제 ────────────────────────────────────────────────────

def test_delete_document_without_auth_returns_401(client):
    resp = client.delete("/api/documents/소득세법(법률).pdf")
    assert resp.status_code == 401


def test_delete_document_success(client, auth_cookie):
    with patch(
        "app.services.upload_service.delete_document",
        AsyncMock(return_value={"status": "ok", "filename": "소득세법(법률).pdf", "deleted_chunks": 42}),
    ):
        resp = client.delete("/api/documents/소득세법(법률).pdf", cookies=auth_cookie)
    assert resp.status_code == 200
    assert resp.json()["deleted_chunks"] == 42


def test_delete_document_not_found_returns_404(client, auth_cookie):
    from fastapi import HTTPException
    with patch(
        "app.services.upload_service.delete_document",
        AsyncMock(side_effect=HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")),
    ):
        resp = client.delete("/api/documents/없는파일.pdf", cookies=auth_cookie)
    assert resp.status_code == 404

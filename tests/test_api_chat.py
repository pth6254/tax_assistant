"""
test_api_chat.py — 채팅 엔드포인트 테스트
"""
import pytest
from unittest.mock import AsyncMock, patch


# ── 인증 검사 ────────────────────────────────────────────────────

def test_chat_without_auth_returns_401(client):
    resp = client.post("/api/chat", json={"query": "소득세율이 어떻게 되나요?"})
    assert resp.status_code == 401


def test_chat_stream_without_auth_returns_401(client):
    resp = client.post("/api/chat/stream", json={"query": "소득세율이 어떻게 되나요?"})
    assert resp.status_code == 401


# ── 유효성 검사 ──────────────────────────────────────────────────

def test_chat_missing_query_returns_422(client, auth_cookie):
    resp = client.post("/api/chat", json={}, cookies=auth_cookie)
    assert resp.status_code == 422


# ── 정상 응답 (서비스 mock) ───────────────────────────────────────

def test_chat_returns_output(client, auth_cookie):
    with patch(
        "app.services.chat_service.process_chat",
        AsyncMock(return_value="소득세 최고세율은 45%입니다."),
    ):
        resp = client.post(
            "/api/chat",
            json={"query": "소득세 최고세율은?"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert "output" in resp.json()
    assert "45%" in resp.json()["output"]


# ── 헬스체크 ─────────────────────────────────────────────────────

def test_health_returns_ok(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = "PostgreSQL 17.0 on x86_64"

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

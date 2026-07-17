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
        AsyncMock(return_value=("소득세 최고세율은 45%입니다.", None)),
    ):
        resp = client.post(
            "/api/chat",
            json={"query": "소득세 최고세율은?", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "45%" in body["output"]
    assert body["calculator"] is None


def test_chat_returns_calculator_metadata_when_present(client, auth_cookie):
    calc_meta = {"tool": "income_tax", "params": {"income": 50000000}}
    with patch(
        "app.services.chat_service.process_chat",
        AsyncMock(return_value=("결정세액은 589만원입니다.", calc_meta)),
    ):
        resp = client.post(
            "/api/chat",
            json={"query": "연소득 5천만원 세금 얼마야?", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert resp.json()["calculator"] == calc_meta


# ── 스트리밍 응답 (서비스 mock) ────────────────────────────────────

def test_chat_stream_emits_chunk_and_calc_events(client, auth_cookie):
    async def fake_stream(query, conversation_id, user_id):
        yield {"type": "chunk", "text": "결정세액은 "}
        yield {"type": "chunk", "text": "589만원입니다."}
        yield {"type": "calc", "tool": "income_tax", "params": {"income": 50000000}}

    with patch("app.services.chat_service.stream_chat_response", fake_stream):
        resp = client.post(
            "/api/chat/stream",
            json={"query": "연소득 5천만원 세금 얼마야?", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert '"type": "chunk"' in resp.text
    assert '"type": "calc"' in resp.text
    assert '"tool": "income_tax"' in resp.text
    assert "[DONE]" in resp.text


# ── 헬스체크 ─────────────────────────────────────────────────────

def test_health_returns_ok(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = "PostgreSQL 17.0 on x86_64"

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

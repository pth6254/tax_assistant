"""
test_api_chat.py — 채팅 엔드포인트 테스트
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch

from app.services.inference.llm.errors import LLMGenerationIncomplete


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

def test_chat_returns_output(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()
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


def test_chat_returns_calculator_metadata_when_present(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()
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

def test_chat_stream_emits_chunk_and_calc_events(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()

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


def test_truncated_stream_emits_error_without_done(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()

    async def fake_stream(query, conversation_id, user_id):
        yield {"type": "chunk", "text": "답변 일부"}
        raise LLMGenerationIncomplete("length")

    with patch("app.services.chat_service.stream_chat_response", fake_stream):
        resp = client.post(
            "/api/chat/stream",
            json={"query": "복합 질문", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert '"code": "generation_incomplete"' in resp.text
    assert "[DONE]" not in resp.text


def test_unexpected_stream_error_is_reported_without_false_done(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()

    async def fake_stream(query, conversation_id, user_id):
        yield {"type": "chunk", "text": "답변 일부"}
        raise RuntimeError("private upstream detail")

    with patch("app.services.chat_service.stream_chat_response", fake_stream):
        resp = client.post(
            "/api/chat/stream",
            json={"query": "테스트", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 200
    assert '"code": "stream_failed"' in resp.text
    assert "private upstream detail" not in resp.text
    assert "[DONE]" not in resp.text


def test_truncated_nonstream_is_502(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()
    with patch("app.services.chat_service.process_chat", AsyncMock(side_effect=LLMGenerationIncomplete("length"))):
        resp = client.post(
            "/api/chat",
            json={"query": "복합 질문", "conversation_id": "00000000-0000-0000-0000-000000000001"},
            cookies=auth_cookie,
        )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "generation_incomplete"


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_chat_rejects_conversation_owned_by_another_user(
    client, auth_cookie, mock_pool, path,
):
    _, conn = mock_pool
    conn.fetchval.return_value = None

    with patch("app.services.chat_service.process_chat", AsyncMock()) as process_chat:
        resp = client.post(
            path,
            json={
                "query": "테스트 질문",
                "conversation_id": "00000000-0000-0000-0000-000000000001",
            },
            cookies=auth_cookie,
        )

    assert resp.status_code == 404
    process_chat.assert_not_awaited()


def test_chat_rejects_malformed_conversation_id(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conn.fetchval.reset_mock()

    resp = client.post(
        "/api/chat",
        json={"query": "테스트 질문", "conversation_id": "not-a-uuid"},
        cookies=auth_cookie,
    )

    assert resp.status_code == 404
    conn.fetchval.assert_not_awaited()


# ── 헬스체크 ─────────────────────────────────────────────────────

def test_health_returns_ok(client, mock_pool):
    _, conn = mock_pool
    conn.fetchval.return_value = "PostgreSQL 17.0 on x86_64"

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.parametrize("stream", [False, True])
def test_provider_error_reaches_chat_without_false_done(client, auth_cookie, mock_pool, stream):
    from app.services.inference.llm.errors import LLMRequestError
    _, conn = mock_pool
    conn.fetchval.return_value = uuid.uuid4()
    error = LLMRequestError("llm_rate_limited", "요청 한도", 429)

    async def failed_stream(*args, **kwargs):
        raise error
        yield

    target = "stream_chat_response" if stream else "process_chat"
    replacement = failed_stream if stream else AsyncMock(side_effect=error)
    with patch(f"app.services.chat_service.{target}", replacement):
        response = client.post("/api/chat/stream" if stream else "/api/chat", json={
            "query": "테스트", "conversation_id": "00000000-0000-0000-0000-000000000001",
        }, cookies=auth_cookie)
    assert response.status_code == (200 if stream else 429)
    assert "llm_rate_limited" in response.text and "[DONE]" not in response.text

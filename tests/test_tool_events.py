import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service
from app.services.tools import planner
from app.services.tools.executor import ToolRun


@pytest.mark.asyncio
async def test_planner_emits_real_lifecycle_without_identity(monkeypatch):
    monkeypatch.setattr(planner, "select_tool", AsyncMock(return_value=("document_search", {"query": "계약"})))
    monkeypatch.setattr(planner, "execute_tool", AsyncMock(return_value=ToolRun("document_search", "not_found", "자료 없음")))
    events = []
    await planner.run_tools_for_query("내 계약서", user_id=str(uuid4()), on_event=events.append)
    assert [e["status"] for e in events] == ["selecting", "running", "not_found"]
    assert all("user_id" not in e.get("params", {}) for e in events)
    assert events[-1]["context"] == "자료 없음"


@pytest.mark.asyncio
async def test_stream_emits_progress_before_preparation_finishes_and_saves_terminal(monkeypatch):
    release = asyncio.Event()
    async def prepare(*args, on_tool_event):
        on_tool_event({"type": "tool", "id": "primary", "tool": "document_search", "status": "running"})
        await release.wait()
        on_tool_event({"type": "tool", "id": "primary", "tool": "document_search", "status": "ok", "context": "자료"})
        return "자료", "웹 검색 생략", [], None
    async def tokens(*args, **kwargs):
        yield "답변"
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context", prepare)
    monkeypatch.setattr(chat_service, "_stream_llm_skip_think", tokens)
    monkeypatch.setattr(chat_service, "_append_source_list_if_missing", AsyncMock(side_effect=lambda a, _: a))
    monkeypatch.setattr(chat_service, "build_citation_footer", lambda *args: "")
    save = AsyncMock()
    monkeypatch.setattr(chat_service, "_save_history", save)
    stream = chat_service.stream_chat_response("내 문서", str(uuid4()), str(uuid4()))
    assert (await asyncio.wait_for(anext(stream), 1))["status"] == "running"
    release.set()
    remaining = [e async for e in stream]
    assert remaining[0]["status"] == "ok"
    assert remaining[1]["type"] == "chunk"
    assert [e["status"] for e in save.call_args.kwargs["tools"]] == ["ok"]


@pytest.mark.asyncio
async def test_disconnect_cancels_pending_tool_task(monkeypatch):
    cancelled = asyncio.Event()
    async def prepare(*args, on_tool_event):
        on_tool_event({"type": "tool", "id": "primary", "tool": "none", "status": "selecting"})
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context", prepare)
    stream = chat_service.stream_chat_response("내 문서", str(uuid4()), str(uuid4()))
    await anext(stream)
    await stream.aclose()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_persistence_keeps_tool_metadata_but_llm_history_excludes_it(mock_pool, monkeypatch):
    pool, conn = mock_pool
    monkeypatch.setattr(chat_service, "get_pool", AsyncMock(return_value=pool))
    tool = {"id": "primary", "tool": "document_search", "status": "ok", "context": "문서"}
    await chat_service._save_history(uuid4(), "질문", "답변", tools=[tool])
    message = json.loads(conn.executemany.call_args.args[1][1][1])
    assert message["tools"] == [tool]
    conn.fetch.return_value = [{"message": message}]
    assert await chat_service._fetch_history(uuid4()) == [{"role": "assistant", "content": "답변"}]


def test_message_reload_restores_tools(client, auth_cookie, mock_pool):
    _, conn = mock_pool
    conv = uuid4()
    conn.fetchval.return_value = conv
    tool = {"id": "primary", "tool": "law_lookup", "status": "ok"}
    conn.fetch.return_value = [{"message": {"role": "assistant", "content": "답변", "tools": [tool]}}]
    response = client.get(f"/api/conversations/{conv}/messages", cookies=auth_cookie)
    assert response.status_code == 200
    assert response.json()[0]["tools"] == [tool]


def test_nonstream_api_returns_terminal_tools(client, auth_cookie, mock_pool, monkeypatch):
    _, conn = mock_pool
    conn.fetchval.return_value = uuid4()
    async def process(*args, tool_events, **kwargs):
        tool_events.extend([{"status": "running"}, {"tool": "law_lookup", "status": "ok"}])
        return "답변", None
    monkeypatch.setattr(chat_service, "process_chat", process)
    response = client.post("/api/chat", json={"query": "조문", "conversation_id": str(uuid4())}, cookies=auth_cookie)
    assert response.json()["tools"] == [{"tool": "law_lookup", "status": "ok"}]

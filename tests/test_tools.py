import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.tool_call import LawLookupRequest
from app.services import chat_service
from app.services.tools import executor, planner, law_lookup, document_search
from app.services.search import hybrid_search_service as search_service

UID = str(uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,params", [
    ("delete_document", {}),
    ("document_search", {"query": "계약", "user_id": str(uuid4())}),
    ("document_search", {"query": "계약", "top_k": 100}),
    ("document_search", {"query": ""}),
    ("law_lookup", {"law_name": "소득세법", "article_no": "잘못된 번호"}),
    ("income_tax", {"income": "1000"}),
])
async def test_invalid_arguments_never_execute(monkeypatch, tool, params):
    search = AsyncMock()
    monkeypatch.setattr(document_search, "search", search)
    result = await executor.execute_tool(tool, params, user_id=UID)
    assert result.status == "invalid_arguments"
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_identity_is_server_injected(monkeypatch):
    search = AsyncMock(return_value=("ok", "자료"))
    monkeypatch.setattr(document_search, "search", search)
    result = await executor.execute_tool("document_search", {"query": "계약"}, user_id=UID)
    assert result.status == "ok"
    assert search.call_args.args[1] == UID


@pytest.mark.asyncio
async def test_missing_identity_is_rejected(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(document_search, "search", search)
    assert (await executor.execute_tool("document_search", {"query": "계약"}, user_id="")).status == "invalid_arguments"
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_and_error_are_safe(monkeypatch):
    monkeypatch.setattr(document_search, "search", AsyncMock(side_effect=TimeoutError))
    result = await executor.execute_tool("document_search", {"query": "계약"}, user_id=UID)
    assert result.status == "timeout"
    monkeypatch.setattr(document_search, "search", AsyncMock(side_effect=RuntimeError("secret")))
    result = await executor.execute_tool("document_search", {"query": "계약"}, user_id=UID)
    assert result.status == "error"
    assert "secret" not in result.context


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed(monkeypatch):
    monkeypatch.setattr(document_search, "search", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await executor.execute_tool("document_search", {"query": "계약"}, user_id=UID)


@pytest.mark.asyncio
async def test_law_target_and_missing_target(monkeypatch):
    article = SimpleNamespace(
        target=SimpleNamespace(exists=True, text="요청한 항 원문"),
        article_text="전체 원문", reference=SimpleNamespace(canonical="소득세법 제59조의4 제9항"),
        source_url="https://example.test", law_name="소득세법", law_type="법률",
        effective_date="2026-01-01",
    )
    lookup = AsyncMock(return_value=article)
    monkeypatch.setattr(law_lookup, "get_law_article", lookup)
    request = LawLookupRequest(law_name="소득세법", article_no="제59조의4 제9항")
    status, text = await law_lookup.lookup(request)
    assert status == "ok" and "요청한 항 원문" in text and "전체 원문" not in text
    lookup.assert_awaited_once_with("소득세법", "제59조의4 제9항")
    article.target.exists = False
    assert (await law_lookup.lookup(request))[0] == "not_found"
    lookup.return_value = None
    assert (await law_lookup.lookup(request))[0] == "not_found"


@pytest.mark.asyncio
async def test_document_service_reuses_scoped_search(monkeypatch):
    monkeypatch.setattr(search_service, "embed_texts", AsyncMock(return_value=[[0.1]]))
    query = AsyncMock(return_value=[])
    monkeypatch.setattr(search_service, "_search_documents", query)
    assert await search_service.search_user_documents("계약", UID, 3) == []
    query.assert_awaited_once_with([0.1], "ALL", 3, UID)
    assert "user_id = $2::uuid" in search_service._DOCUMENTS_SQL


@pytest.mark.asyncio
async def test_tool_query_does_not_repeat_rag(monkeypatch):
    monkeypatch.setattr(chat_service, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_service, "run_tools_for_query", AsyncMock(
        return_value=executor.ToolRun("document_search", "not_found", "관련 자료 없음"),
    ))
    search = AsyncMock()
    monkeypatch.setattr(chat_service, "hybrid_search", search)
    context, web, _, calc = await chat_service._fetch_rag_and_web_context("내 문서", uuid4(), UID)
    assert "관련 자료 없음" in context and web == "웹 검색 생략" and calc is None
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_selection_single_execution(monkeypatch):
    select = AsyncMock(return_value=("document_search", {"query": "계약서"}))
    execute = AsyncMock(return_value=executor.ToolRun("document_search", "ok", "본문"))
    monkeypatch.setattr(planner, "select_tool", select)
    monkeypatch.setattr(planner, "execute_tool", execute)
    await planner.run_tools_for_query("내 계약서", user_id=UID)
    select.assert_awaited_once()
    execute.assert_awaited_once_with("document_search", {"query": "계약서"}, user_id=UID)


@pytest.mark.asyncio
async def test_actual_selection_chain_uses_history(monkeypatch):
    generate = AsyncMock(return_value='{"tool":"law_lookup","params":{"law_name":"소득세법","article_no":"제59조의4 제9항"}}')
    monkeypatch.setattr(planner, "call_llm", generate)
    history = [{"role": "user", "content": "소득세법을 알려줘"}]
    selection = await planner.select_tool("제59조의4 제9항 원문", history)
    assert selection[1]["article_no"] == "제59조의4 제9항"
    assert history[0] in generate.call_args.args[0]


@pytest.mark.asyncio
async def test_document_result_preserves_source_without_inventing_page(monkeypatch):
    from app.schemas.tool_call import DocumentSearchRequest
    monkeypatch.setattr(document_search, "search_user_documents", AsyncMock(return_value=[
        SimpleNamespace(source="계약서.pdf", content="지급일은 매월 말일"),
    ]))
    status, context = await document_search.search(DocumentSearchRequest(query="지급일"), UID)
    assert status == "ok"
    assert "계약서.pdf" in context and "지급일은 매월 말일" in context
    assert "페이지" not in context


@pytest.mark.asyncio
async def test_law_context_truncation_is_disclosed(monkeypatch):
    monkeypatch.setattr(law_lookup, "lookup", AsyncMock(return_value=("ok", "가" * 13000)))
    result = await executor.execute_tool("law_lookup", {"law_name": "소득세법", "article_no": "제55조"}, user_id=UID)
    assert "일부 생략" in result.context and len(result.context) < 12500

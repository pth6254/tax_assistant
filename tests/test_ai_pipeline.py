"""Composition, strict output validation and streaming without a model SDK."""
import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.exceptions import OutputParserException

from app.schemas.ai_output import CitationList, QueryClassification
from app.services import chat_service
from app.services.ai_pipeline import chat_prompt, output_parser, streaming_chain, text_chain, to_provider_messages
from app.services.calculator import engine


def test_prompt_preserves_json_braces_and_history_roles():
    prompt = chat_prompt('JSON example: {"ok": true}', "{query}", history=True)
    history = [{"role": "user", "content": "{old}"}, {"role": "assistant", "content": "answer"}]
    messages = to_provider_messages(prompt.invoke({"history": history, "query": "{new}"}))
    assert messages == [
        {"role": "system", "content": 'JSON example: {"ok": true}'},
        *history, {"role": "user", "content": "{new}"},
    ]
    with pytest.raises(KeyError):
        prompt.invoke({"history": []})


@pytest.mark.asyncio
async def test_named_chain_supports_local_callbacks_and_plain_callable():
    names = []

    class Observer(BaseCallbackHandler):
        def on_chain_start(self, serialized, inputs, **kwargs):
            names.append(kwargs.get("name"))

    complete = AsyncMock(return_value="answer")
    chain = text_chain(chat_prompt("system", "{query}"), complete, name="test_answer")
    assert await chain.ainvoke({"query": "hello"}, config={"callbacks": [Observer()]}) == "answer"
    complete.assert_awaited_once_with([
        {"role": "system", "content": "system"}, {"role": "user", "content": "hello"},
    ])
    assert {"test_answer", "test_answer_prompt", "provider_messages", "test_answer_generate"} <= set(names)


@pytest.mark.asyncio
async def test_stream_delivers_first_chunk_before_generation_finishes():
    release = asyncio.Event()

    async def stream(messages):
        assert messages[-1]["content"] == "hello"
        yield "first"
        await release.wait()
        yield "second"

    chain = streaming_chain(chat_prompt("system", "{query}"), stream, name="test_stream")
    chunks = chain.astream({"query": "hello"})
    try:
        assert await asyncio.wait_for(anext(chunks), timeout=5) == "first"
        release.set()
        assert [part async for part in chunks] == ["second"]
    finally:
        release.set()
        await chunks.aclose()


@pytest.mark.parametrize("raw", [
    '{"law":"ALL","queries":["one"]',  # No automatic repair of truncated JSON.
    '{"law":"ALL","queries":"one"}',
    '{"law":"ALL","queries":[3]}',
    '{"law":"ALL","queries":[" "]}',
    '{"law":"ALL","queries":["one"],"unexpected":true}',
    '{"queries":["one"]}',
])
def test_invalid_classification_is_rejected(raw):
    with pytest.raises((ValueError, OutputParserException)):
        output_parser(QueryClassification).invoke(raw)


def test_complete_fenced_json_is_accepted():
    result = output_parser(QueryClassification).invoke(
        '<think>internal</think>```json\n{"law":"ALL","queries":[" query "]}\n```'
    )
    assert result.queries == ["query"]


@pytest.mark.parametrize("citation", [
    {"label": "unknown", "law_name": "소득세법", "article_no": "제55조"},
    {"label": "법률", "law_name": "소득세법", "article_no": "제55조 제1항"},
    {"label": "법률", "law_name": "", "article_no": "제55조"},
])
def test_citation_schema_validates_labels_and_article_format(citation):
    with pytest.raises(OutputParserException):
        output_parser(CitationList).invoke({"citations": [citation]})


@pytest.mark.asyncio
async def test_invalid_classification_falls_back_without_retry(monkeypatch):
    call = AsyncMock(return_value='{"law":"ALL","queries":[2]}')
    monkeypatch.setattr(chat_service, "call_llm", call)
    assert await chat_service._classify_and_generate_queries("기준이 어떻게 되나요?") == (
        "ALL", ["기준이 어떻게 되나요?"],
    )
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_keyword_classification_still_skips_llm(monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(chat_service, "call_llm", call)
    assert await chat_service._classify_and_generate_queries("소득세 신고") == ("소득세법", ["소득세 신고"])
    call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [
    {}, {"income": "50000000"}, {"income": 50000000, "invented": 1},
])
async def test_invalid_tool_inputs_never_reach_calculator(monkeypatch, params):
    monkeypatch.setattr(engine, "call_llm", AsyncMock(return_value=json.dumps({"tool": "income_tax", "params": params})))
    calculate = AsyncMock()
    monkeypatch.setattr(engine.income_tax, "calculate", calculate)
    assert await engine.run_calculation_for_query("소득 5000만원 세금 계산해줘") is None
    calculate.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_tool_extraction_preserves_params(monkeypatch):
    call = AsyncMock(return_value='{"tool":"income_tax","params":{"income":50000000}}')
    monkeypatch.setattr(engine, "call_llm", call)
    assert await engine.extract_calculation_request("소득 5000만원") == ("income_tax", {"income": 50000000})
    assert call.call_args.kwargs == {"temperature": 0.0, "max_tokens": 400}


@pytest.mark.asyncio
async def test_chat_pipeline_keeps_guard_and_history_storage(monkeypatch):
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context", AsyncMock(return_value=("자료", "웹 검색 생략", [], None)))
    monkeypatch.setattr(chat_service, "call_llm", AsyncMock(return_value="original"))
    monkeypatch.setattr(chat_service, "_append_source_list_if_missing", AsyncMock(return_value="patched"))
    monkeypatch.setattr(chat_service, "apply_citation_guard", lambda answer, context, calc: answer + " guarded")
    save = AsyncMock()
    monkeypatch.setattr(chat_service, "_save_history", save)
    conv_id = uuid4()
    assert await chat_service.process_chat("질문", str(conv_id), "test-user") == ("patched guarded", None)
    save.assert_awaited_once_with(conv_id, "질문", "patched guarded", is_first=True)


@pytest.mark.asyncio
async def test_streaming_chat_keeps_footer_events_and_saved_answer(monkeypatch):
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context", AsyncMock(return_value=("자료", "웹 검색 생략", [], None)))

    async def stream(messages, temperature=0.3):
        yield "hello "
        yield "world"

    monkeypatch.setattr(chat_service, "_stream_llm_skip_think", stream)
    monkeypatch.setattr(chat_service, "_append_source_list_if_missing", AsyncMock(return_value="hello world"))
    monkeypatch.setattr(chat_service, "build_citation_footer", lambda *args: " footer")
    save = AsyncMock()
    monkeypatch.setattr(chat_service, "_save_history", save)
    conv_id = uuid4()
    events = [e async for e in chat_service.stream_chat_response("질문", str(conv_id), "test-user")]
    await asyncio.gather(*list(chat_service._bg_tasks))
    assert events == [
        {"type": "chunk", "text": "hello "}, {"type": "chunk", "text": "world"},
        {"type": "chunk", "text": " footer"},
    ]
    save.assert_awaited_once_with(conv_id, "질문", "hello world footer", is_first=True)

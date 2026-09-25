"""Provider-neutral LLM client tests."""
import json
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from app.services import llm_client
from app.services.inference.llm.errors import LLMGenerationIncomplete
from app.services.inference.llm.factory import create_llm_provider
from app.services.inference.llm.policy import llm_purpose
from config import LLM_REMOTE_MAX_TOKENS


def set_task(monkeypatch, name, **changes):
    settings = llm_client.LLM_TASK_SETTINGS.copy()
    settings[name] = replace(settings[name], **changes)
    monkeypatch.setattr(llm_client, "LLM_TASK_SETTINGS", settings)


@pytest_asyncio.fixture(autouse=True)
async def reset_provider():
    await llm_client.close_llm_client()
    yield
    await llm_client.close_llm_client()


@pytest.mark.asyncio
async def test_llamacpp_chat_uses_openai_compatible_endpoint(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == llm_client.LLM_TASK_SETTINGS["answer"].model
        assert payload["max_tokens"] == 42
        assert payload["chat_template_kwargs"] == {"enable_thinking": llm_client.LLM_TASK_SETTINGS["answer"].think_enabled}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "테스트 답변"}}]},
        )

    client = httpx.AsyncClient(
        base_url="http://llama-chat:8080/v1/",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    set_task(monkeypatch, "answer", provider="llamacpp", base_url="http://llama-chat:8080/v1", api_key="test-key")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)

    result = await llm_client.call_llm(
        [{"role": "user", "content": "질문"}], max_tokens=42
    )

    assert result == "테스트 답변"
    await llm_client.close_llm_client()


@pytest.mark.asyncio
async def test_llamacpp_chat_reuses_openai_compatible_endpoint(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = httpx.AsyncClient(
        base_url="http://llama-chat:8080/v1/",
        transport=httpx.MockTransport(handler),
    )
    set_task(monkeypatch, "answer", provider="llamacpp", base_url="http://llama-chat:8080/v1")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)

    assert await llm_client.call_llm([{"role": "user", "content": "질문"}]) == "ok"
    assert await llm_client.call_llm([{"role": "user", "content": "다음 질문"}]) == "ok"
    await llm_client.close_llm_client()


@pytest.mark.asyncio
async def test_llamacpp_structured_output_sends_json_schema(monkeypatch):
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["schema"] == schema
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
        )

    client = httpx.AsyncClient(
        base_url="http://llama-chat:8080/v1/",
        transport=httpx.MockTransport(handler),
    )
    set_task(monkeypatch, "answer", provider="llamacpp", base_url="http://llama-chat:8080/v1")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)

    result = await llm_client.call_llm_structured([], schema)

    assert result == {"answer": "ok"}
    await llm_client.close_llm_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["ollama", "llamacpp", "openrouter"])
async def test_facade_selects_endpoint_reuses_provider_and_closes(monkeypatch, provider_name):
    provider = Mock()
    provider.complete = AsyncMock(return_value="ok")
    provider.close = AsyncMock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(llm_client, "create_llm_provider", factory)
    expected_url = "http://ollama.test" if provider_name == "ollama" else "http://compatible.test/v1"
    set_task(monkeypatch, "answer", provider=provider_name, base_url=expected_url,
             api_key="test-key" if provider_name == "openrouter" else "local-key")

    await llm_client.call_llm([], max_tokens=42)
    await llm_client.call_llm([], max_tokens=42)
    factory.assert_called_once()
    assert factory.call_args.kwargs["base_url"] == expected_url
    assert factory.call_args.kwargs["api_key"] == ("test-key" if provider_name == "openrouter" else "local-key")
    provider.complete.assert_awaited_with([], 0.3, 42)
    await llm_client.close_llm_client()
    await llm_client.close_llm_client()
    provider.close.assert_awaited_once()
    assert not llm_client._provider_instances


@pytest.mark.asyncio
async def test_each_task_selects_its_model_and_reuses_matching_provider(monkeypatch):
    answer = Mock(complete=AsyncMock(return_value="answer"), structured=AsyncMock(return_value={}), close=AsyncMock())
    routing = Mock(complete=AsyncMock(return_value="route"), structured=AsyncMock(return_value={}), close=AsyncMock())
    factory = Mock(side_effect=[routing, answer])
    monkeypatch.setattr(llm_client, "create_llm_provider", factory)
    set_task(monkeypatch, "tool_selection", model="openai/gpt-5-nano", reasoning_effort="minimal")
    set_task(monkeypatch, "query_classification", model="openai/gpt-5-nano", reasoning_effort="minimal")

    assert await llm_client.call_llm([], purpose="tool_selection") == "route"
    assert await llm_client.call_llm([], purpose="query_classification") == "route"
    assert await llm_client.call_llm([], purpose="answer") == "answer"
    await llm_client.call_llm_structured([], {}, purpose="citation_extraction")
    assert [call.kwargs["model"] for call in factory.call_args_list] == [
        "openai/gpt-5-nano", "openai/gpt-6-luna",
    ]
    assert routing.complete.await_count == 2
    answer.complete.assert_awaited_once()
    answer.structured.assert_awaited_once()
    await llm_client.close_llm_client()
    routing.close.assert_awaited_once()
    answer.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_matching_task_settings_share_provider(monkeypatch):
    provider = Mock(complete=AsyncMock(return_value="ok"), close=AsyncMock())
    factory = Mock(return_value=provider)
    monkeypatch.setattr(llm_client, "create_llm_provider", factory)
    set_task(monkeypatch, "tool_selection", **{
        field: getattr(llm_client.LLM_TASK_SETTINGS["answer"], field)
        for field in ("provider", "model", "base_url", "api_key", "timeout_sec", "reasoning_effort",
                      "think_enabled", "temperature", "max_tokens")
    })
    await llm_client.call_llm([], purpose="tool_selection")
    await llm_client.call_llm([], purpose="answer")
    factory.assert_called_once()
    await llm_client.close_llm_client()
    provider.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_routing_can_use_local_ollama_while_answer_uses_openrouter(monkeypatch):
    routing = Mock(complete=AsyncMock(return_value="route"), close=AsyncMock())
    factory = Mock(return_value=routing)
    monkeypatch.setattr(llm_client, "create_llm_provider", factory)
    set_task(monkeypatch, "tool_selection", provider="ollama", model="qwen3.5:9b",
             base_url="http://ollama.windows.host:11434", reasoning_effort=None)
    assert await llm_client.call_llm([], purpose="tool_selection") == "route"
    assert factory.call_args.kwargs["base_url"] == "http://ollama.windows.host:11434"
    assert factory.call_args.kwargs["model"] == "qwen3.5:9b"
    await llm_client.close_llm_client()


@pytest.mark.asyncio
async def test_openrouter_free_model_complete_structured_and_stream(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "openrouter/free"
        assert "chat_template_kwargs" not in payload
        requests.append(payload)
        if payload.get("stream"):
            return httpx.Response(200, text=(
                'data: {"choices":[{"delta":{"content":"답변"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ))
        if "response_format" in payload:
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"확인"}'}, "finish_reason": "stop"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "완료"}, "finish_reason": "stop"}]})

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider(
        "openrouter", base_url="https://openrouter.ai/api/v1", api_key="test-key",
        model="openrouter/free", timeout=30, thinking=False,
    )
    try:
        assert await provider.complete([], 0.3, 128) == "완료"
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        assert await provider.structured([], schema, 0, 64) == {"answer": "확인"}
        assert [part async for part in provider.stream([], 0.3, 128)] == ["답변"]
        assert requests[1]["response_format"]["type"] == "json_schema"
        assert requests[1]["provider"] == {"require_parameters": True}
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_openrouter_gpt5_nano_uses_minimal_reasoning_without_temperature(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "openai/gpt-5-nano"
        assert payload["reasoning_effort"] == "minimal"
        assert "temperature" not in payload
        return httpx.Response(200, json={"choices": [{
            "message": {"content": '{"tool":"none"}'}, "finish_reason": "stop",
        }]})

    client = httpx.AsyncClient(base_url="https://openrouter.ai/api/v1/", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider("openrouter", base_url="https://openrouter.ai/api/v1",
                                   api_key="test-key", model="openai/gpt-5-nano", timeout=30, thinking=False)
    try:
        assert await provider.complete([], 0, 1024) == '{"tool":"none"}'
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_explicit_task_effort_overrides_model_default(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "openai/gpt-6-luna"
        assert payload["reasoning_effort"] == "medium"
        assert "temperature" not in payload
        return httpx.Response(200, json={"choices": [{
            "message": {"content": "ok"}, "finish_reason": "stop",
        }]})

    client = httpx.AsyncClient(base_url="https://openrouter.ai/api/v1/", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider("openrouter", base_url="https://openrouter.ai/api/v1",
                                   api_key="test-key", model="openai/gpt-6-luna", timeout=30,
                                   thinking=False, reasoning_effort="medium")
    try:
        assert await provider.complete([], 0, 512) == "ok"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_openrouter_gpt6_luna_model_parameters(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "openai/gpt-6-luna"
        assert "temperature" not in payload
        if payload.get("stream"):
            return httpx.Response(200, text=(
                'data: {"choices":[{"delta":{"content":"답변"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ))
        if "response_format" in payload:
            return httpx.Response(200, json={"choices": [{
                "message": {"content": '{"ok":true}'}, "finish_reason": "stop",
            }]})
        return httpx.Response(200, json={"choices": [{
            "message": {"content": "답변"}, "finish_reason": "stop",
        }]})

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider(
        "openrouter", base_url="https://openrouter.ai/api/v1", api_key="test-key",
        model="openai/gpt-6-luna", timeout=30, thinking=False,
    )
    try:
        token = llm_purpose.set("tool_selection")
        try:
            assert await provider.complete([], 0.3, 1024) == "답변"
        finally:
            llm_purpose.reset(token)
        assert await provider.structured([], {"type": "object"}, 0.0, 800) == {"ok": True}
        assert [part async for part in provider.stream([], 0.3, -1)] == ["답변"]
        assert [p["reasoning_effort"] for p in requests] == ["none", "low", "low"]
        assert requests[0]["max_tokens"] == 1024
        assert requests[2]["max_tokens"] == LLM_REMOTE_MAX_TOKENS
        assert requests[1]["response_format"]["type"] == "json_schema"
    finally:
        await provider.close()


def test_openrouter_requires_key():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_llm_provider(
            "openrouter", base_url="https://openrouter.ai/api/v1", api_key="",
            model="openrouter/free", timeout=30, thinking=False,
        )


def test_openai_requires_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_llm_provider(
            "openai", base_url="https://api.openai.com/v1", api_key="",
            model="gpt-6-luna", timeout=30, thinking=False,
        )


@pytest.mark.asyncio
async def test_openrouter_length_finish_reason_is_not_success(monkeypatch):
    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "미완성"}, "finish_reason": "length"}],
        })),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider(
        "openrouter", base_url="https://openrouter.ai/api/v1", api_key="test-key",
        model="openrouter/free", timeout=30, thinking=False,
    )
    try:
        with pytest.raises(LLMGenerationIncomplete, match="length"):
            await provider.complete([], 0.3, 64)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_complete_length_keeps_partial_for_answer_continuation(monkeypatch):
    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "first part"}, "finish_reason": "length"}],
        })),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider("openrouter", base_url="https://openrouter.ai/api/v1",
                                   api_key="test-key", model="openai/gpt-6-luna",
                                   timeout=30, thinking=False)
    try:
        with pytest.raises(LLMGenerationIncomplete) as error:
            await provider.complete([], 0.3, 64)
        assert error.value.partial_content == "first part"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_stream_length_yields_final_delta_before_incomplete(monkeypatch):
    body = ('data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":" last"},"finish_reason":"length"}]}\n\n'
            'data: [DONE]\n\n')
    client = httpx.AsyncClient(base_url="https://openrouter.ai/api/v1/",
                               transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider("openrouter", base_url="https://openrouter.ai/api/v1",
                                   api_key="test-key", model="openai/gpt-6-luna",
                                   timeout=30, thinking=False)
    parts = []
    try:
        with pytest.raises(LLMGenerationIncomplete, match="length"):
            async for part in provider.stream([], 0.3, 64):
                parts.append(part)
        assert parts == ["first", " last"]
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_openrouter_structured_retries_invalid_content_once(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = None if calls == 1 else '{"ok":true}'
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        })

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/", transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider(
        "openrouter", base_url="https://openrouter.ai/api/v1", api_key="test-key",
        model="openrouter/free", timeout=30, thinking=False,
    )
    try:
        assert await provider.structured([], {"type": "object"}, 0, 512) == {"ok": True}
        assert calls == 2
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_openrouter_structured_rejects_two_invalid_responses(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}],
        })

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1/", transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    provider = create_llm_provider(
        "openrouter", base_url="https://openrouter.ai/api/v1", api_key="test-key",
        model="openrouter/free", timeout=30, thinking=False,
    )
    try:
        with pytest.raises(LLMGenerationIncomplete, match="invalid_structured_output"):
            await provider.structured([], {"type": "object"}, 0, 512)
        assert calls == 2
    finally:
        await provider.close()

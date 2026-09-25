"""Provider-neutral LLM client tests."""
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from app.services import llm_client
from app.services.inference.llm.errors import LLMGenerationIncomplete
from app.services.inference.llm.factory import create_llm_provider


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
        assert payload["model"] == llm_client.CHAT_MODEL
        assert payload["max_tokens"] == 42
        assert payload["chat_template_kwargs"] == {"enable_thinking": llm_client.THINK_ENABLED}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "테스트 답변"}}]},
        )

    client = httpx.AsyncClient(
        base_url="http://llama-chat:8080/v1/",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "llamacpp")
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
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "llamacpp")
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
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "llamacpp")
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
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", provider_name)
    monkeypatch.setattr(llm_client, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(llm_client, "LLM_BASE_URL", "http://compatible.test/v1")
    monkeypatch.setattr(llm_client, "OPENROUTER_API_KEY", "test-key")

    await llm_client.call_llm([], max_tokens=42)
    await llm_client.call_llm([], max_tokens=42)
    factory.assert_called_once()
    expected_url = "http://ollama.test" if provider_name == "ollama" else "http://compatible.test/v1"
    assert factory.call_args.kwargs["base_url"] == expected_url
    assert factory.call_args.kwargs["api_key"] == ("test-key" if provider_name == "openrouter" else llm_client.LLM_API_KEY)
    provider.complete.assert_awaited_with([], 0.3, 42)
    await llm_client.close_llm_client()
    await llm_client.close_llm_client()
    provider.close.assert_awaited_once()
    assert llm_client._provider_instance is None


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


def test_openrouter_requires_key():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_llm_provider(
            "openrouter", base_url="https://openrouter.ai/api/v1", api_key="",
            model="openrouter/free", timeout=30, thinking=False,
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

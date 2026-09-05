"""Provider-neutral LLM client tests."""
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from app.services import llm_client


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
@pytest.mark.parametrize("provider_name", ["ollama", "llamacpp"])
async def test_facade_selects_endpoint_reuses_provider_and_closes(monkeypatch, provider_name):
    provider = Mock()
    provider.complete = AsyncMock(return_value="ok")
    provider.close = AsyncMock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(llm_client, "create_llm_provider", factory)
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", provider_name)
    monkeypatch.setattr(llm_client, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(llm_client, "LLM_BASE_URL", "http://compatible.test/v1")

    await llm_client.call_llm([], max_tokens=42)
    await llm_client.call_llm([], max_tokens=42)
    factory.assert_called_once()
    expected_url = "http://ollama.test" if provider_name == "ollama" else "http://compatible.test/v1"
    assert factory.call_args.kwargs["base_url"] == expected_url
    provider.complete.assert_awaited_with([], 0.3, 42)
    await llm_client.close_llm_client()
    await llm_client.close_llm_client()
    provider.close.assert_awaited_once()
    assert llm_client._provider_instance is None

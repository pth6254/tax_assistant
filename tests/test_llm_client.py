"""Provider-neutral LLM client tests."""
import json

import httpx
import pytest

from app.services import llm_client


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
    monkeypatch.setattr(llm_client, "_http_client", client)

    result = await llm_client.call_llm(
        [{"role": "user", "content": "질문"}], num_predict=42
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
    monkeypatch.setattr(llm_client, "_http_client", client)

    assert await llm_client.call_llm([{"role": "user", "content": "질문"}]) == "ok"
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
    monkeypatch.setattr(llm_client, "_http_client", client)

    result = await llm_client.call_llm_structured([], schema)

    assert result == {"answer": "ok"}
    await llm_client.close_llm_client()

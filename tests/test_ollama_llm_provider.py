"""Ollama wire contract, failure handling and resource cleanup without ChatOllama."""
import json

import httpx
import pytest
import pytest_asyncio

from app.services.inference.llm.factory import create_llm_provider


@pytest_asyncio.fixture
async def provider():
    instance = create_llm_provider(
        "ollama", base_url="http://ollama.test/", model="test-model",
        num_ctx=4096, keep_alive=-1, thinking=False, timeout=37.0,
    )
    yield instance
    await instance.close()


async def mock_http(provider, handler):
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_complete_preserves_ollama_settings_and_history(provider):
    assert provider._client.timeout.read == 37.0
    messages = [{"role": "system", "content": "규칙"}, {"role": "user", "content": "질문"}]

    def handler(request):
        assert str(request.url) == "http://ollama.test/api/chat"
        assert json.loads(request.content) == {
            "model": "test-model", "messages": messages, "stream": False,
            "think": False, "keep_alive": -1,
            "options": {"temperature": 0.3, "num_predict": -1, "num_ctx": 4096},
        }
        return httpx.Response(200, json={"message": {"content": "답변", "thinking": "비공개"}})

    await mock_http(provider, handler)
    assert await provider.complete(messages, 0.3, -1) == "답변"
    await provider.close()
    assert provider._client.is_closed


@pytest.mark.asyncio
async def test_structured_sends_schema_and_returns_object(provider):
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

    def handler(request):
        payload = json.loads(request.content)
        assert payload["format"] == schema
        assert payload["stream"] is False
        assert payload["options"]["num_predict"] == 64
        return httpx.Response(200, json={"message": {"content": '{"answer":"확인"}'}})

    await mock_http(provider, handler)
    assert await provider.structured([], schema, 0.0, 64) == {"answer": "확인"}


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not json", "[]", "null"])
async def test_structured_rejects_invalid_object(provider, content):
    await mock_http(provider, lambda request: httpx.Response(200, json={"message": {"content": content}}))
    with pytest.raises(ValueError):
        await provider.structured([], {"type": "object"}, 0.0, 64)


@pytest.mark.asyncio
async def test_stream_ndjson_excludes_thinking_and_keeps_final_content(provider):
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text='\n{"message":{"thinking":"비공개","content":""},"done":false}\n'
                              '{"message":{"content":"안녕"},"done":false}\n'
                              '{"message":{"content":"하세요"},"done":true}\n')

    await mock_http(provider, handler)
    assert [part async for part in provider.stream([], 0.3, 64)] == ["안녕", "하세요"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_http_errors_propagate(provider, stream):
    await mock_http(provider, lambda request: httpx.Response(404, json={"error": "missing model"}))
    with pytest.raises(httpx.HTTPStatusError):
        if stream:
            _ = [part async for part in provider.stream([], 0.0, 64)]
        else:
            await provider.complete([], 0.0, 64)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    '{"error":"generation failed"}\n',
    '{"message":{"content":"partial"},"done":false}\n',
])
async def test_failed_or_truncated_stream_does_not_succeed(provider, body):
    await mock_http(provider, lambda request: httpx.Response(200, text=body))
    with pytest.raises(RuntimeError):
        _ = [part async for part in provider.stream([], 0.0, 64)]

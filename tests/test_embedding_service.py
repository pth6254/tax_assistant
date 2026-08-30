import json

import httpx
import pytest

from app.services.inference.embedding.factory import create_embedding_provider


@pytest.mark.asyncio
async def test_ollama_embedding_does_not_request_permanent_residency():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content)
        assert payload == {"model": "model", "input": ["세무 상담"]}
        assert "keep_alive" not in payload
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})

    provider = create_embedding_provider("ollama", "http://ollama", "model", 10)
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await provider.embed(["세무 상담"]) == [[0.1, 0.2]]
    await provider.close()


@pytest.mark.asyncio
async def test_llamacpp_embedding_uses_openai_compatible_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        payload = json.loads(request.content)
        assert payload == {
            "model": "qwen3-embedding:4b-gguf",
            "input": ["소득세법"],
            "encoding_format": "float",
        }
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    provider = create_embedding_provider(
        "llamacpp", "http://llama-embedding:8080/v1", "qwen3-embedding:4b-gguf", 10
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await provider.embed(["소득세법"]) == [[0.1, 0.2]]
    await provider.close()


def test_unknown_embedding_provider_is_rejected():
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        create_embedding_provider("unknown", "http://example", "model", 10)

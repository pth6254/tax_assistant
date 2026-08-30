"""Backward-compatible facade for the configured LLM provider."""
from typing import AsyncGenerator

from app.services.inference.llm import create_llm_provider
from config import (
    CHAT_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_PROVIDER,
    LLM_TIMEOUT_SEC,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX,
    THINK_ENABLED,
)

_provider_instance = None
_provider_key = None
_http_client = None  # Backward-compatible test injection point.


def _get_provider():
    global _provider_instance, _provider_key
    key = (LLM_PROVIDER, LLM_BASE_URL, OLLAMA_BASE_URL, CHAT_MODEL)
    if _provider_instance is None or _provider_key != key:
        _provider_instance = create_llm_provider(
            LLM_PROVIDER,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=CHAT_MODEL,
            timeout=LLM_TIMEOUT_SEC,
            thinking=THINK_ENABLED,
            ollama_base_url=OLLAMA_BASE_URL,
            num_ctx=OLLAMA_NUM_CTX,
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        if _http_client is not None and hasattr(_provider_instance, "_client"):
            _provider_instance._client = _http_client
        _provider_key = key
    return _provider_instance


async def close_llm_client() -> None:
    global _provider_instance, _provider_key, _http_client
    if _provider_instance is not None:
        await _provider_instance.close()
    _provider_instance = None
    _provider_key = None
    _http_client = None


async def call_llm(messages: list[dict], temperature: float = 0.3, num_predict: int = -1) -> str:
    return await _get_provider().complete(messages, temperature, num_predict)


async def call_llm_structured(
    messages: list[dict], schema: dict, temperature: float = 0.0, num_predict: int = -1,
) -> dict:
    return await _get_provider().structured(messages, schema, temperature, num_predict)


async def stream_llm(
    messages: list[dict], temperature: float = 0.3, num_predict: int = -1,
) -> AsyncGenerator[str, None]:
    async for chunk in _get_provider().stream(messages, temperature, num_predict):
        yield chunk

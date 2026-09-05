"""Provider-neutral generation API; configuration is fixed for the process lifetime."""
from typing import AsyncGenerator

from app.services.inference.llm import create_llm_provider
from app.services.inference.llm.base import LLMProvider
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

_provider_instance: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = create_llm_provider(
            LLM_PROVIDER,
            base_url=OLLAMA_BASE_URL if LLM_PROVIDER == "ollama" else LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=CHAT_MODEL,
            timeout=LLM_TIMEOUT_SEC,
            thinking=THINK_ENABLED,
            num_ctx=OLLAMA_NUM_CTX,
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
    return _provider_instance


async def close_llm_client() -> None:
    global _provider_instance
    if _provider_instance is not None:
        await _provider_instance.close()
    _provider_instance = None


async def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = -1) -> str:
    return await _get_provider().complete(messages, temperature, max_tokens)


async def call_llm_structured(
    messages: list[dict], schema: dict, temperature: float = 0.0, max_tokens: int = -1,
) -> dict:
    return await _get_provider().structured(messages, schema, temperature, max_tokens)


async def stream_llm(
    messages: list[dict], temperature: float = 0.3, max_tokens: int = -1,
) -> AsyncGenerator[str, None]:
    async for chunk in _get_provider().stream(messages, temperature, max_tokens):
        yield chunk

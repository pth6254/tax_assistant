"""Provider-neutral generation API with independent settings for each AI task."""
from typing import AsyncGenerator

from app.services.inference.llm import create_llm_provider
from app.services.inference.llm.base import LLMProvider
from app.services.inference.llm.policy import llm_purpose
from config import LLM_TASK_SETTINGS, LLMTaskSettings, OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX

_provider_instances: dict[LLMTaskSettings, LLMProvider] = {}


def _settings(purpose: str) -> LLMTaskSettings:
    try:
        return LLM_TASK_SETTINGS[purpose]
    except KeyError as exc:
        raise ValueError(f"Unknown LLM task: {purpose}") from exc


def _get_provider(purpose: str = "answer") -> LLMProvider:
    settings = _settings(purpose)
    if settings not in _provider_instances:
        _provider_instances[settings] = create_llm_provider(
            settings.provider,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            timeout=settings.timeout_sec,
            thinking=settings.think_enabled,
            num_ctx=OLLAMA_NUM_CTX,
            keep_alive=OLLAMA_KEEP_ALIVE,
            reasoning_effort=settings.reasoning_effort,
        )
    return _provider_instances[settings]


async def close_llm_client() -> None:
    providers = list({id(provider): provider for provider in _provider_instances.values()}.values())
    _provider_instances.clear()
    for provider in providers:
        await provider.close()


def _limits(purpose: str, temperature: float, max_tokens: int) -> tuple[float, int]:
    settings = _settings(purpose)
    return (settings.temperature if settings.temperature is not None else temperature,
            settings.max_tokens if settings.max_tokens is not None else max_tokens)


async def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = -1, *, purpose: str = "answer") -> str:
    token = llm_purpose.set(purpose)
    try:
        temperature, max_tokens = _limits(purpose, temperature, max_tokens)
        return await _get_provider(purpose).complete(messages, temperature, max_tokens)
    finally:
        llm_purpose.reset(token)


async def call_llm_structured(
    messages: list[dict], schema: dict, temperature: float = 0.0, max_tokens: int = -1,
    *, purpose: str = "answer",
) -> dict:
    token = llm_purpose.set(purpose)
    try:
        temperature, max_tokens = _limits(purpose, temperature, max_tokens)
        return await _get_provider(purpose).structured(messages, schema, temperature, max_tokens)
    finally:
        llm_purpose.reset(token)


async def stream_llm(
    messages: list[dict], temperature: float = 0.3, max_tokens: int = -1, *, purpose: str = "answer",
) -> AsyncGenerator[str, None]:
    token = llm_purpose.set(purpose)
    try:
        temperature, max_tokens = _limits(purpose, temperature, max_tokens)
        async for chunk in _get_provider(purpose).stream(messages, temperature, max_tokens):
            yield chunk
    finally:
        llm_purpose.reset(token)

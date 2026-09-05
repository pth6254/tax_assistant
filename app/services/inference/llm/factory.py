from .base import LLMProvider
from .ollama import OllamaLLMProvider
from .openai_compatible import OpenAICompatibleLLMProvider


def create_llm_provider(
    provider: str,
    *,
    base_url: str,
    model: str,
    timeout: float,
    thinking: bool,
    api_key: str = "",
    num_ctx: int = 4096,
    keep_alive: int = -1,
) -> LLMProvider:
    if provider == "ollama":
        return OllamaLLMProvider(
            base_url=base_url, model=model, num_ctx=num_ctx,
            keep_alive=keep_alive, thinking=thinking, timeout=timeout,
        )
    if provider in {"llamacpp", "openai", "openai-compatible"}:
        return OpenAICompatibleLLMProvider(
            base_url=base_url, api_key=api_key, model=model,
            timeout=timeout, thinking=thinking,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")

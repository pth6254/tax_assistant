from .base import LLMProvider
from .ollama import OllamaLLMProvider
from .openai_compatible import OpenAICompatibleLLMProvider


def create_llm_provider(provider: str, **settings) -> LLMProvider:
    if provider == "ollama":
        return OllamaLLMProvider(
            settings["ollama_base_url"], settings["model"], settings["num_ctx"],
            settings["keep_alive"], settings["thinking"],
        )
    if provider in {"llamacpp", "openai", "openai-compatible"}:
        return OpenAICompatibleLLMProvider(
            settings["base_url"], settings["api_key"], settings["model"],
            settings["timeout"], settings["thinking"],
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")

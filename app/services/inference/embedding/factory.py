from .base import EmbeddingProvider
from .ollama import OllamaEmbeddingProvider
from .openai_compatible import OpenAICompatibleEmbeddingProvider


def create_embedding_provider(
    provider: str,
    base_url: str,
    model: str,
    timeout: float,
) -> EmbeddingProvider:
    if provider == "ollama":
        return OllamaEmbeddingProvider(base_url, model, timeout)
    if provider in {"llamacpp", "openai", "openai-compatible"}:
        return OpenAICompatibleEmbeddingProvider(base_url, model, timeout)
    raise ValueError(f"Unsupported embedding provider: {provider}")

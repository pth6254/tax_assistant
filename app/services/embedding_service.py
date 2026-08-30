"""Backward-compatible facade for provider-neutral embedding clients."""
import asyncio
from app.services.inference.embedding import create_embedding_provider
from config import (
    EMBED_DIM,
    EMBEDDING_BASE_URL,
    EMBEDDING_DUAL_WRITE,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    EMBEDDING_TIMEOUT_SEC,
    EMBEDDING_VERSION,
    EMBEDDING_V1_BASE_URL,
    EMBEDDING_V1_MODEL,
    EMBEDDING_V1_PROVIDER,
    EMBEDDING_V2_BASE_URL,
    EMBEDDING_V2_MODEL,
    EMBEDDING_V2_PROVIDER,
)

_providers = {}


def _provider(provider: str, base_url: str, model: str):
    key = (provider, base_url, model)
    if key not in _providers:
        _providers[key] = create_embedding_provider(
            provider, base_url, model, EMBEDDING_TIMEOUT_SEC
        )
    return _providers[key]


def get_embedding_provider(version: str | None = None):
    if version == "v1":
        return _provider(EMBEDDING_V1_PROVIDER, EMBEDDING_V1_BASE_URL, EMBEDDING_V1_MODEL)
    if version == "v2":
        return _provider(EMBEDDING_V2_PROVIDER, EMBEDDING_V2_BASE_URL, EMBEDDING_V2_MODEL)
    return _provider(EMBEDDING_PROVIDER, EMBEDDING_BASE_URL, EMBEDDING_MODEL)


def _validate(vectors: list[list[float]], expected_count: int) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise ValueError(f"Embedding count mismatch: expected {expected_count}, got {len(vectors)}")
    for vector in vectors:
        if len(vector) != EMBED_DIM:
            raise ValueError(f"Embedding dimension mismatch: expected {EMBED_DIM}, got {len(vector)}")
    return vectors


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _validate(await get_embedding_provider().embed(texts), len(texts))


async def embed_texts_for_version(texts: list[str], version: str) -> list[list[float]]:
    if version not in {"v1", "v2"}:
        raise ValueError("version must be 'v1' or 'v2'")
    if not texts:
        return []
    return _validate(await get_embedding_provider(version).embed(texts), len(texts))


async def embed_texts_for_storage(
    texts: list[str],
) -> tuple[list[list[float]] | None, list[list[float]] | None]:
    """Return vectors for the legacy and v2 columns, optionally dual-writing."""
    if EMBEDDING_DUAL_WRITE:
        v1, v2 = await asyncio.gather(
            embed_texts_for_version(texts, "v1"),
            embed_texts_for_version(texts, "v2"),
        )
        return v1, v2
    vectors = await embed_texts(texts)
    return (None, vectors) if EMBEDDING_VERSION == "v2" else (vectors, None)


async def close_http_client() -> None:
    providers = list(_providers.values())
    _providers.clear()
    for provider in providers:
        await provider.close()

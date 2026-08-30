from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def health(self) -> dict: ...
    async def close(self) -> None: ...

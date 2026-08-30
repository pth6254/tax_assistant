import httpx


class OpenAICompatibleEmbeddingProvider:
    """Embedding client for llama.cpp and other OpenAI-compatible servers."""

    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._http().post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts, "encoding_format": "float"},
        )
        response.raise_for_status()
        items = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]

    async def health(self) -> dict:
        response = await self._http().get(f"{self.base_url}/models", timeout=3.0)
        response.raise_for_status()
        models = {item.get("id") for item in response.json().get("data", [])}
        return {"connected": True, "model_available": self.model in models}

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

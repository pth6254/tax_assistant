import httpx


class OllamaEmbeddingProvider:
    name = "ollama"

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
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    async def health(self) -> dict:
        response = await self._http().get(f"{self.base_url}/api/tags", timeout=3.0)
        response.raise_for_status()
        models = {item.get("name") for item in response.json().get("models", [])}
        return {"connected": True, "model_available": self.model in models}

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

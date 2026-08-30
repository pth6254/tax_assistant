import json
from typing import AsyncGenerator

from langchain_ollama import ChatOllama


class OllamaLLMProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, num_ctx: int, keep_alive: int, thinking: bool):
        self.base_url = base_url
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.thinking = thinking

    def _client(self, temperature: float, max_tokens: int, schema: dict | None = None):
        return ChatOllama(
            model=self.model, base_url=self.base_url, temperature=temperature,
            num_predict=max_tokens, num_ctx=self.num_ctx, keep_alive=self.keep_alive,
            reasoning=self.thinking, format=schema,
        )

    async def complete(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        return (await self._client(temperature, max_tokens).ainvoke(messages)).content

    async def structured(self, messages: list[dict], schema: dict, temperature: float, max_tokens: int) -> dict:
        result = await self._client(temperature, max_tokens, schema).ainvoke(messages)
        return json.loads(result.content)

    async def stream(self, messages: list[dict], temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
        async for chunk in self._client(temperature, max_tokens).astream(messages):
            if chunk.content:
                yield chunk.content

    async def close(self) -> None:
        return None

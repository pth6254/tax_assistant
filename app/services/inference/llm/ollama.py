import json
from typing import AsyncGenerator

import httpx


class OllamaLLMProvider:
    name = "ollama"

    def __init__(
        self, base_url: str, model: str, num_ctx: int,
        keep_alive: int, thinking: bool, timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.thinking = thinking
        self._client = httpx.AsyncClient(timeout=timeout)

    def _payload(self, messages: list[dict], temperature: float, max_tokens: int) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.thinking,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            },
        }

    @staticmethod
    def _check_error(data: dict) -> None:
        # Ollama can report errors inside an already-started HTTP 200 stream.
        if "error" in data:
            raise RuntimeError(f"Ollama generation failed: {data['error']}")

    async def _complete(self, payload: dict) -> str:
        response = await self._client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        self._check_error(data)
        return data["message"]["content"]

    async def complete(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        return await self._complete(self._payload(messages, temperature, max_tokens))

    async def structured(self, messages: list[dict], schema: dict, temperature: float, max_tokens: int) -> dict:
        payload = self._payload(messages, temperature, max_tokens)
        payload["format"] = schema
        result = json.loads(await self._complete(payload))
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object from Ollama structured output")
        return result

    async def stream(self, messages: list[dict], temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                self._check_error(data)
                # Thinking output is separate from the user-visible answer.
                content = data.get("message", {}).get("content")
                if content:
                    yield content
                if data.get("done"):
                    return
            raise RuntimeError("Ollama stream ended before completion")

    async def close(self) -> None:
        await self._client.aclose()

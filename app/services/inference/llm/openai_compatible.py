import json
from typing import AsyncGenerator

import httpx


class OpenAICompatibleLLMProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, thinking: bool):
        self.model = model
        self.thinking = thinking
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def _payload(self, messages: list[dict], temperature: float, max_tokens: int) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": self.thinking},
        }
        if max_tokens >= 0:
            payload["max_tokens"] = max_tokens
        return payload

    async def complete(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        response = await self._client.post("chat/completions", json=self._payload(messages, temperature, max_tokens))
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def structured(self, messages: list[dict], schema: dict, temperature: float, max_tokens: int) -> dict:
        payload = self._payload(messages, temperature, max_tokens)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "structured_response", "strict": True, "schema": schema},
        }
        response = await self._client.post("chat/completions", json=payload)
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])

    async def stream(self, messages: list[dict], temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        async with self._client.stream("POST", "chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                content = json.loads(data)["choices"][0]["delta"].get("content")
                if content:
                    yield content

    async def close(self) -> None:
        await self._client.aclose()

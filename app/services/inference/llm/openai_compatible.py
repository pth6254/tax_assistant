import json
from typing import AsyncGenerator

import httpx

from app.services.inference.llm.errors import LLMGenerationIncomplete


class OpenAICompatibleLLMProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, thinking: bool, provider: str = "llamacpp"):
        self.model = model
        self.thinking = thinking
        self.provider = provider
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
        }
        if self.provider == "llamacpp":
            payload["chat_template_kwargs"] = {"enable_thinking": self.thinking}
        if max_tokens >= 0:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _choice(data: dict) -> dict:
        if "error" in data:
            raise RuntimeError("LLM provider returned an error")
        choice = data["choices"][0]
        reason = choice.get("finish_reason")
        if reason and reason != "stop":
            raise LLMGenerationIncomplete(reason)
        return choice

    async def complete(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        response = await self._client.post("chat/completions", json=self._payload(messages, temperature, max_tokens))
        response.raise_for_status()
        content = self._choice(response.json())["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMGenerationIncomplete("empty_content")
        return content

    async def structured(self, messages: list[dict], schema: dict, temperature: float, max_tokens: int) -> dict:
        payload = self._payload(messages, temperature, max_tokens)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "structured_response", "strict": True, "schema": schema},
        }
        if self.provider == "openrouter":
            payload["provider"] = {"require_parameters": True}
        attempts = 2 if self.provider == "openrouter" else 1
        for _ in range(attempts):
            response = await self._client.post("chat/completions", json=payload)
            response.raise_for_status()
            content = self._choice(response.json())["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                return result
        raise LLMGenerationIncomplete("invalid_structured_output")

    async def stream(self, messages: list[dict], temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        async with self._client.stream("POST", "chat/completions", json=payload) as response:
            response.raise_for_status()
            completed = False
            has_content = False
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    completed = True
                    break
                event = json.loads(data)
                if "error" in event:
                    raise RuntimeError("LLM provider returned a streaming error")
                if not event.get("choices"):
                    continue
                choice = self._choice(event)
                content = choice["delta"].get("content")
                if content:
                    has_content = True
                    yield content
            if not completed:
                raise RuntimeError("LLM stream ended before completion")
            if not has_content:
                raise LLMGenerationIncomplete("empty_content")

    async def close(self) -> None:
        await self._client.aclose()

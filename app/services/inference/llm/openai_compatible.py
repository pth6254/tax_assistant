import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import AsyncGenerator

import httpx

from app.services.inference.llm.errors import LLMGenerationIncomplete, LLMRequestError
from app.services.inference.llm.policy import EXTRACTION_PURPOSES, llm_purpose
from config import LLM_REMOTE_MAX_TOKENS

logger = logging.getLogger(__name__)


class OpenAICompatibleLLMProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, thinking: bool,
                 provider: str = "llamacpp", reasoning_effort: str | None = None):
        self.model = model
        self.thinking = thinking
        self.provider = provider
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self._usage_totals: dict[str, float | int] = {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def _payload(self, messages: list[dict], temperature: float, max_tokens: int) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if self.reasoning_effort is not None and self.provider in {"openrouter", "openai", "openai-compatible"}:
            payload["reasoning_effort"] = self.reasoning_effort
        elif self.provider == "openrouter" and self.model == "openai/gpt-6-luna":
            # Extraction and answer generation have different reasoning needs.
            payload["reasoning_effort"] = "none" if llm_purpose.get() in EXTRACTION_PURPOSES else "low"
        elif self.provider == "openrouter" and self.model == "openai/gpt-5-nano":
            # GPT-5 nano is a reasoning model; temperature is not supported.
            payload["reasoning_effort"] = "minimal"
        else:
            payload["temperature"] = temperature
        if self.provider == "llamacpp":
            payload["chat_template_kwargs"] = {"enable_thinking": self.thinking}
        if self.provider in {"openrouter", "openai", "openai-compatible"}:
            max_tokens = min(max_tokens, LLM_REMOTE_MAX_TOKENS) if max_tokens >= 0 else LLM_REMOTE_MAX_TOKENS
        if max_tokens >= 0:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float | None:
        value = response.headers.get("Retry-After")
        try:
            delay = float(value) if value is not None else float(2 ** attempt)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return None
        # Do not retry earlier than the upstream's requested wait.
        return max(0.0, delay) if math.isfinite(delay) and delay <= 4 else None

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise LLMRequestError("llm_rate_limited", "AI 제공자의 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", 429)
        if response.status_code == 402:
            raise LLMRequestError("llm_credit_required", "AI 제공자 잔액 또는 사용 한도를 확인해야 합니다. 관리자에게 문의해 주세요.", 503)
        if response.is_error:
            raise LLMRequestError("llm_provider_error", "AI 제공자 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.")

    @asynccontextmanager
    async def _response(self, payload: dict):
        """Retry only rejected HTTP 429, never a started stream or timeout."""
        try:
            async with asyncio.timeout(self.timeout):
                for attempt in range(3):
                    async with self._client.stream("POST", "chat/completions", json=payload) as response:
                        delay = self._retry_delay(response, attempt) if response.status_code == 429 else None
                        if response.status_code != 429 or attempt == 2 or delay is None:
                            self._check_status(response)
                            yield response
                            return
                    logger.warning("LLM rate limit provider=%s retry=%d", self.provider, attempt + 1)
                    await asyncio.sleep(delay)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise LLMRequestError("llm_timeout", "AI 응답 제한 시간이 초과되었습니다. 질문을 나누어 다시 시도해 주세요.", 504) from exc
        except httpx.TransportError as exc:
            raise LLMRequestError("llm_connection_error", "AI 제공자와 연결이 끊겼습니다. 잠시 후 다시 시도해 주세요.") from exc

    def _record_usage(self, data: dict) -> None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        # Numeric metadata only: no prompts, answers, API keys or provider bodies.
        safe = {k: v for k, v in usage.items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens", "cost"}
                and type(v) in {int, float}}
        for key, value in safe.items():
            self._usage_totals[key] = self._usage_totals.get(key, 0) + value
        logger.info("LLM usage provider=%s model=%s purpose=%s metrics=%s",
                    self.provider, self.model, llm_purpose.get(), safe)

    def usage_snapshot(self) -> dict[str, float | int]:
        """Provider-reported totals only; a missing cost is not zero cost."""
        return dict(self._usage_totals)

    async def _json_response(self, payload: dict) -> dict:
        async with self._response(payload) as response:
            await response.aread()
            data = response.json()
            self._record_usage(data)
            return data

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
        data = await self._json_response(self._payload(messages, temperature, max_tokens))
        if data.get("choices") and data["choices"][0].get("finish_reason") == "length":
            partial = data["choices"][0].get("message", {}).get("content")
            raise LLMGenerationIncomplete("length", partial if isinstance(partial, str) else "")
        content = self._choice(data)["message"].get("content")
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
            data = await self._json_response(payload)
            content = self._choice(data)["message"].get("content")
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
        if self.provider == "openrouter":
            payload["stream_options"] = {"include_usage": True}
        async with self._response(payload) as response:
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
                self._record_usage(event)
                if "error" in event:
                    raise RuntimeError("LLM provider returned a streaming error")
                if not event.get("choices"):
                    continue
                choice = event["choices"][0]
                content = choice["delta"].get("content")
                if content:
                    has_content = True
                    yield content
                # Preserve content in the final length event before resuming.
                self._choice(event)
            if not completed:
                raise RuntimeError("LLM stream ended before completion")
            if not has_content:
                raise LLMGenerationIncomplete("empty_content")

    async def close(self) -> None:
        await self._client.aclose()

"""Remote inference budgets, rejected-request retries and privacy regressions."""
import asyncio
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import llm_client
from app.services.inference.llm import openai_compatible as adapter
from app.services.inference.llm.errors import LLMRequestError
from app.services.inference.llm.policy import llm_purpose


def provider_for(monkeypatch, handler, *, timeout=1):
    client = httpx.AsyncClient(base_url="https://example.test/v1/", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(adapter.httpx, "AsyncClient", lambda **kwargs: client)
    return adapter.OpenAICompatibleLLMProvider("https://example.test/v1", "secret", "openai/gpt-6-luna", timeout, False, "openrouter")


def success():
    return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_429_before_generation_retries_at_most_twice(monkeypatch, stream):
    calls = []
    sleep = AsyncMock()
    monkeypatch.setattr(adapter.asyncio, "sleep", sleep)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "private"})

    provider = provider_for(monkeypatch, handler)
    try:
        with pytest.raises(LLMRequestError) as error:
            if stream:
                _ = [chunk async for chunk in provider.stream([], 0, -1)]
            else:
                await provider.complete([], 0, -1)
        assert error.value.code == "llm_rate_limited"
        assert len(calls) == 3 and sleep.await_count == 2
        assert "private" not in str(error.value)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_retry_can_recover(monkeypatch):
    calls = []
    monkeypatch.setattr(adapter.asyncio, "sleep", AsyncMock())

    def handler(request):
        calls.append(request)
        return httpx.Response(429) if len(calls) == 1 else success()

    provider = provider_for(monkeypatch, handler)
    try:
        assert await provider.complete([], 0, -1) == "ok"
        assert len(calls) == 2
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,header,code", [
    (429, "3600", "llm_rate_limited"), (429, "nan", "llm_rate_limited"),
    (402, "0", "llm_credit_required"), (401, "0", "llm_provider_error"),
])
async def test_long_wait_and_other_http_errors_do_not_retry(monkeypatch, status, header, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": header})

    provider = provider_for(monkeypatch, handler)
    try:
        with pytest.raises(LLMRequestError) as error:
            await provider.complete([], 0, -1)
        assert error.value.code == code and len(calls) == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_partial_stream_error_never_replays_or_succeeds(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=(
            'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            'data: {"error":{"code":429,"message":"private"}}\n\n'
        ))

    provider = provider_for(monkeypatch, handler)
    parts = []
    try:
        with pytest.raises(RuntimeError):
            async for part in provider.stream([], 0, 32):
                parts.append(part)
        assert parts == ["partial"] and len(calls) == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_whole_request_deadline_and_no_timeout_retry(monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.1)
        return success()

    provider = provider_for(monkeypatch, handler, timeout=0.01)
    try:
        with pytest.raises(LLMRequestError) as error:
            await provider.complete([], 0, -1)
        assert error.value.code == "llm_timeout" and len(calls) == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_stream_usage_only_logs_numeric_metadata(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=adapter.__name__)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream_options"] == {"include_usage": True}
        assert payload["max_tokens"] == adapter.LLM_REMOTE_MAX_TOKENS
        return httpx.Response(200, text=(
            'data: {"choices":[{"delta":{"content":"private-answer"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"cost":0.01,"secret":"private-data"}}\n\n'
            'data: [DONE]\n\n'
        ))

    provider = provider_for(monkeypatch, handler)
    try:
        assert [p async for p in provider.stream([{"role": "user", "content": "private-query"}], 0, 999999)]
        assert "prompt_tokens" in caplog.text and "cost" in caplog.text
        assert "private-" not in caplog.text
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_purpose_is_reset_on_failure(monkeypatch):
    async def fail(*args):
        assert llm_purpose.get() == "tool_selection"
        raise RuntimeError("failure")

    class Provider:
        complete = staticmethod(fail)

    monkeypatch.setattr(llm_client, "_get_provider", lambda purpose: Provider())
    with pytest.raises(RuntimeError):
        await llm_client.call_llm([], purpose="tool_selection")
    assert llm_purpose.get() == "answer"

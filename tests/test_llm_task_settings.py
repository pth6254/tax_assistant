"""Task-level model selection, parameter overrides, and validation."""
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest

import config
from app.services import llm_client


def test_task_names_cover_all_application_llm_calls():
    assert set(config.LLM_TASK_SETTINGS) == {
        "answer", "history_answer", "citation_extraction", "query_classification",
        "tool_selection", "document_classification",
    }


def test_task_settings_accept_independent_provider_model_and_limits(monkeypatch):
    prefix = "LLM_TASK_DOCUMENT_CLASSIFICATION_"
    monkeypatch.setenv(prefix + "PROVIDER", "ollama")
    monkeypatch.setenv(prefix + "MODEL", "qwen3.5:9b")
    monkeypatch.setenv(prefix + "THINK_ENABLED", "true")
    monkeypatch.setenv(prefix + "MAX_TOKENS", "256")
    monkeypatch.setenv(prefix + "TEMPERATURE", "0")
    settings = config._task_settings("document_classification")
    assert (settings.provider, settings.model, settings.base_url) == (
        "ollama", "qwen3.5:9b", config.OLLAMA_BASE_URL,
    )
    assert settings.think_enabled is True
    assert settings.max_tokens == 256
    assert settings.temperature == 0
    assert "api_key" not in repr(settings)


@pytest.mark.parametrize("suffix,value", [
    ("PROVIDER", "unsupported"), ("REASONING_EFFORT", "invalid"),
    ("TIMEOUT_SEC", "0"), ("MAX_TOKENS", "-1"),
])
def test_invalid_task_settings_fail_fast(monkeypatch, suffix, value):
    monkeypatch.setenv("LLM_TASK_ANSWER_" + suffix, value)
    with pytest.raises(ValueError):
        config._task_settings("answer")


@pytest.mark.asyncio
async def test_task_overrides_are_applied_to_completion_and_stream(monkeypatch):
    provider = Mock(complete=AsyncMock(return_value="ok"), close=AsyncMock())

    async def chunks(*args):
        yield "stream"

    provider.stream = chunks
    settings = llm_client.LLM_TASK_SETTINGS.copy()
    settings["answer"] = replace(settings["answer"], temperature=0.1, max_tokens=123)
    monkeypatch.setattr(llm_client, "LLM_TASK_SETTINGS", settings)
    monkeypatch.setattr(llm_client, "create_llm_provider", Mock(return_value=provider))
    try:
        assert await llm_client.call_llm([]) == "ok"
        assert [item async for item in llm_client.stream_llm([])] == ["stream"]
        provider.complete.assert_awaited_once_with([], 0.1, 123)
    finally:
        await llm_client.close_llm_client()


@pytest.mark.asyncio
async def test_unknown_task_cannot_select_arbitrary_provider():
    with pytest.raises(ValueError, match="Unknown LLM task"):
        await llm_client.call_llm([], purpose="attacker_selected")

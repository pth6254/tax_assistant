"""A length stop resumes once without persisting or citing partial output."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service
from app.services.inference.llm import continuation
from app.services.inference.llm.errors import LLMGenerationIncomplete, LLMRequestError


@pytest.mark.asyncio
async def test_nonstream_length_resumes_and_stitches_once():
    calls = []

    async def generate(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            raise LLMGenerationIncomplete("length", "## 결론\n첫 문장")
        return "첫 문장 다음 문장\n## 근거 출처 목록\n확인된 근거 없음"

    answer = await continuation.complete_answer([{"role": "user", "content": "질문"}], generate=generate)
    assert answer == "## 결론\n첫 문장 다음 문장\n## 근거 출처 목록\n확인된 근거 없음"
    assert calls[1][-2] == {"role": "assistant", "content": "## 결론\n첫 문장"}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_only_length_resumes_and_exhaustion_never_returns_partial(monkeypatch):
    monkeypatch.setattr(continuation, "LLM_MAX_CONTINUATIONS", 1)
    calls = []

    async def generate(messages, **kwargs):
        calls.append(messages)
        raise LLMGenerationIncomplete("length", f"partial-{len(calls)}")

    with pytest.raises(LLMGenerationIncomplete, match="continuation_limit"):
        await continuation.complete_answer([], generate=generate)
    assert len(calls) == 2

    calls.clear()

    async def failure(messages, **kwargs):
        calls.append(messages)
        raise LLMRequestError("llm_rate_limited", "한도", 429)

    with pytest.raises(LLMRequestError):
        await continuation.complete_answer([], generate=failure)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_stream_length_resumes_without_repeating_tail(monkeypatch):
    calls = []

    async def stream(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            yield "제목\n본문 첫 문장"
            raise LLMGenerationIncomplete("length")
        yield "첫 문장 다음 문장\n근거 목록"

    monkeypatch.setattr(continuation, "stream_llm", stream)
    result = "".join([part async for part in continuation.stream_answer([{"role": "user", "content": "질문"}])])
    assert result == "제목\n본문 첫 문장 다음 문장\n근거 목록"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_stream_exhaustion_raises_and_does_not_repeat_errors(monkeypatch):
    monkeypatch.setattr(continuation, "LLM_MAX_CONTINUATIONS", 1)
    calls = []

    async def stream(messages, **kwargs):
        calls.append(messages)
        yield "partial" if len(calls) == 1 else " more"
        raise LLMGenerationIncomplete("length")

    monkeypatch.setattr(continuation, "stream_llm", stream)
    parts = []
    with pytest.raises(LLMGenerationIncomplete, match="continuation_limit"):
        async for part in continuation.stream_answer([]):
            parts.append(part)
    assert "".join(parts) == "partial more" and len(calls) == 2


@pytest.mark.asyncio
async def test_unfinished_generation_is_never_saved(monkeypatch):
    from app.services.evidence import context_from_records
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context",
                        AsyncMock(return_value=(context_from_records([]), "웹 검색 생략", [], None)))
    monkeypatch.setattr(chat_service, "_answer_evidence_context",
                        AsyncMock(side_effect=LLMGenerationIncomplete("length", "partial")))
    save = AsyncMock()
    monkeypatch.setattr(chat_service, "_save_history", save)
    with pytest.raises(LLMGenerationIncomplete):
        await chat_service.process_chat("질문", str(uuid4()), "test-user")
    save.assert_not_awaited()


def test_chat_trace_has_query_and_conversation_without_user_identifier():
    inputs = chat_service._trace_chat_inputs({"query": "질문", "conversation_id": "id", "user_id": "private", "regeneration": None})
    assert inputs == {"query": "질문", "conversation_id": "id", "regeneration": False}
    assert chat_service._trace_stream_output([{"type": "chunk", "text": "임시"},
                                              {"type": "replace", "text": "검증된 답변"}]) == {"answer": "검증된 답변"}

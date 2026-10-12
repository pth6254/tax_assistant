"""Composition and strict output validation without a model SDK."""
import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.exceptions import OutputParserException

from typing import Literal

from pydantic import Field

from app.schemas.ai_output import AIOutput, NonEmptyText
from app.services import chat_service
from app.services.ai_pipeline import chat_prompt, output_parser, text_chain, to_provider_messages
from app.services.calculator import engine
from app.services.tools import planner


def test_prompt_preserves_json_braces_and_history_roles():
    prompt = chat_prompt('JSON example: {"ok": true}', "{query}", history=True)
    history = [{"role": "user", "content": "{old}"}, {"role": "assistant", "content": "answer"}]
    messages = to_provider_messages(prompt.invoke({"history": history, "query": "{new}"}))
    assert messages == [
        {"role": "system", "content": 'JSON example: {"ok": true}'},
        *history, {"role": "user", "content": "{new}"},
    ]
    with pytest.raises(KeyError):
        prompt.invoke({"history": []})


@pytest.mark.asyncio
async def test_named_chain_supports_local_callbacks_and_plain_callable():
    names = []

    class Observer(BaseCallbackHandler):
        def on_chain_start(self, serialized, inputs, **kwargs):
            names.append(kwargs.get("name"))

    complete = AsyncMock(return_value="answer")
    chain = text_chain(chat_prompt("system", "{query}"), complete, name="test_answer")
    assert await chain.ainvoke({"query": "hello"}, config={"callbacks": [Observer()]}) == "answer"
    complete.assert_awaited_once_with([
        {"role": "system", "content": "system"}, {"role": "user", "content": "hello"},
    ])
    assert {"test_answer", "test_answer_prompt", "provider_messages", "test_answer_generate"} <= set(names)


class QueryClassification(AIOutput):
    """A sample strict schema; the parser is shared by every structured model call."""
    law: NonEmptyText
    queries: list[NonEmptyText] = Field(min_length=1, max_length=3)


class Citation(AIOutput):
    label: Literal["법률", "시행령", "시행규칙"]
    law_name: NonEmptyText = Field(max_length=30)
    article_no: str = Field(pattern=r"^제[0-9]{1,4}조(의[0-9]{1,3})?$")


class CitationList(AIOutput):
    citations: list[Citation]


@pytest.mark.parametrize("raw", [
    '{"law":"ALL","queries":["one"]',  # No automatic repair of truncated JSON.
    '{"law":"ALL","queries":"one"}',
    '{"law":"ALL","queries":[3]}',
    '{"law":"ALL","queries":[" "]}',
    '{"law":"ALL","queries":["one"],"unexpected":true}',
    '{"queries":["one"]}',
])
def test_invalid_classification_is_rejected(raw):
    with pytest.raises((ValueError, OutputParserException)):
        output_parser(QueryClassification).invoke(raw)


def test_complete_fenced_json_is_accepted():
    result = output_parser(QueryClassification).invoke(
        '<think>internal</think>```json\n{"law":"ALL","queries":[" query "]}\n```'
    )
    assert result.queries == ["query"]


@pytest.mark.parametrize("citation", [
    {"label": "unknown", "law_name": "소득세법", "article_no": "제55조"},
    {"label": "법률", "law_name": "소득세법", "article_no": "제55조 제1항"},
    {"label": "법률", "law_name": "", "article_no": "제55조"},
])
def test_citation_schema_validates_labels_and_article_format(citation):
    with pytest.raises(OutputParserException):
        output_parser(CitationList).invoke({"citations": [citation]})


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [
    {}, {"income": "50000000"}, {"income": 50000000, "invented": 1},
])
async def test_invalid_tool_inputs_never_reach_calculator(monkeypatch, params):
    monkeypatch.setattr(planner, "call_llm", AsyncMock(return_value=json.dumps({"tool": "income_tax", "params": params})))
    calculate = AsyncMock()
    monkeypatch.setattr(engine.income_tax, "calculate", calculate)
    result = await planner.run_tools_for_query("소득 5000만원 세금 계산해줘", user_id=str(uuid4()))
    assert result.calculation is None
    assert result.status == ("needs_input" if not params else "invalid_arguments")
    calculate.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_tool_extraction_preserves_params(monkeypatch):
    call = AsyncMock(return_value='{"tool":"income_tax","params":{"income":50000000}}')
    monkeypatch.setattr(planner, "call_llm", call)
    assert await planner.select_tool("소득 5000만원") == ("income_tax", {"income": 50000000})
    assert call.call_args.kwargs == {"temperature": 0.0, "max_tokens": 1024, "purpose": "tool_selection"}


@pytest.fixture
def verified_answer(monkeypatch):
    from app.services.evidence import context_from_records
    from app.services.calculator.engine import CalcRun
    calc = CalcRun("- 결정세액: 1,000원", "income_tax", {"wage_income": 1})
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context",
                        AsyncMock(return_value=(context_from_records([]), "웹 검색 생략", [], calc)))
    verification = {"status": "checked", "citations": []}
    monkeypatch.setattr(chat_service, "_answer_evidence_context", AsyncMock(return_value=("검증된 답변", verification)))
    save = AsyncMock()
    monkeypatch.setattr(chat_service, "_save_history", save)
    return save, verification


@pytest.mark.asyncio
async def test_chat_stores_the_verified_answer_with_its_verification(verified_answer):
    save, verification = verified_answer
    conv_id = uuid4()
    answer, calc = await chat_service.process_chat("질문", str(conv_id), "test-user")
    assert (answer, calc) == ("검증된 답변", {"tool": "income_tax", "params": {"wage_income": 1}})
    assert save.await_args.args == (conv_id, "질문", "검증된 답변")
    assert save.await_args.kwargs["verification"] == verification


@pytest.mark.asyncio
async def test_streaming_chat_sends_the_verified_answer_once_then_saves_it(verified_answer):
    save, verification = verified_answer
    conv_id = uuid4()
    events = [e async for e in chat_service.stream_chat_response("질문", str(conv_id), "test-user")]
    assert [event["type"] for event in events] == ["chunk", "verification", "calc"]
    assert events[0]["text"] == "검증된 답변" and events[1]["data"] == verification
    assert save.await_args.args == (conv_id, "질문", "검증된 답변")


@pytest.mark.asyncio
async def test_a_context_without_server_evidence_is_never_answered(monkeypatch):
    monkeypatch.setattr(chat_service, "_fetch_rag_and_web_context", AsyncMock(return_value=("자료", "웹 검색 생략", [], None)))
    monkeypatch.setattr(chat_service, "_save_history", AsyncMock())
    with pytest.raises(TypeError):
        await chat_service.process_chat("질문", str(uuid4()), "test-user")

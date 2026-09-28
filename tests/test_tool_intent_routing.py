"""General tax questions must reach retrieval, even after a calculation turn."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service as chat
from app.services.evidence import context_from_records
from app.services.tools import planner
from app.services.tools.executor import ToolRun


INFORMATION_QUESTIONS = [
    "부가가치세법 제39조의 매입세액 불공제 요건은?",
    "연매출 1억원이면 매입세액 공제를 받을 수 있나요?",
    "증여 3억원의 세액공제 요건을 설명해줘",
    "계약서 2페이지에 적을 내용은 무엇인가요?",
    "상속세 신고 시 첨부해야 하는 서류는?",
    "소득세 계산 방법을 예시 2개로 설명해줘",
    "2026년 제1기 부가가치세 매입세액 공제 요건은?",
    "국내 자료 보관 의무는 어떻게 되나요?",
    "첨부서류는 몇 년 동안 보관해야 하나요?",
    "소득세법 제55조의 세액 산출 구조를 설명해줘",
    "관련 근거 조문을 찾아줘",
    "파일을 어떻게 업로드하나요?",
    "부가가치세법 원문 조회 방법을 알려줘",
]


@pytest.mark.parametrize("query", INFORMATION_QUESTIONS)
def test_information_requests_are_not_tool_execution(query):
    assert not planner.has_tool_intent(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", INFORMATION_QUESTIONS)
async def test_information_requests_reach_rag_without_none_abstention(monkeypatch, query):
    select = AsyncMock(return_value=None)
    monkeypatch.setattr(planner, "select_tool", select)
    context = context_from_records([])
    prepare = AsyncMock(return_value=context)
    monkeypatch.setattr(chat, "prepare_context", prepare)
    events = []
    result, _, _, _ = await chat._fetch_rag_and_web_context(
        query, uuid4(), str(uuid4()), history_override=[], on_tool_event=events.append)
    assert result is context
    prepare.assert_awaited_once()
    select.assert_not_awaited()
    assert chat._failed_tool_answer(events) is None


@pytest.mark.parametrize("query", [
    "종합소득세 계산해줘", "소득 5000만원이면 세금 얼마야?",
    "10억원 상속받으면 상속세 얼마나 내야 하나요?",
    "매출 5000만원 부가세 납부액을 알려줘", "세액을 계산해주세요",
])
def test_actual_amount_requests_still_require_calculator(query):
    assert planner.has_calculation_intent(query)


@pytest.mark.parametrize("query", ["소득세법 제55조 원문", "소득세법 제55조 보여줘",
                                   "내 계약서", "첨부파일 요약해줘"])
def test_actual_lookup_and_document_requests_still_use_tools(query):
    assert planner.has_tool_intent(query)


@pytest.mark.asyncio
async def test_explanation_after_calculation_does_not_inherit_numeric_intent(monkeypatch):
    history = [{"role": "user", "content": "소득 5000만원 종합소득세 계산해줘"}]
    select = AsyncMock(return_value=None)
    monkeypatch.setattr(planner, "select_tool", select)
    assert await planner.run_tools_for_query("그럼 6000만원일 때 공제 요건은?", user_id=str(uuid4()), history=history) is None
    select.assert_not_awaited()
    assert planner.is_calculation_followup("그럼 6000만원이면?", history)


@pytest.mark.asyncio
async def test_none_cannot_turn_explicit_document_search_into_missing_input(monkeypatch):
    monkeypatch.setattr(planner, "select_tool", AsyncMock(return_value=None))
    execute = AsyncMock(return_value=ToolRun("document_search", "not_found", "자료 없음"))
    monkeypatch.setattr(planner, "execute_tool", execute)
    uid = str(uuid4())
    result = await planner.run_tools_for_query("내 계약서 요약해줘", user_id=uid)
    assert result.status == "not_found"
    execute.assert_awaited_once_with("document_search", {"query": "내 계약서 요약해줘"}, user_id=uid)


@pytest.mark.asyncio
async def test_real_missing_calculation_inputs_remain_blocked_with_specific_message(monkeypatch):
    monkeypatch.setattr(planner, "select_tool", AsyncMock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(planner, "execute_tool", execute)
    events = []
    result = await planner.run_tools_for_query("종합소득세 계산해줘", user_id=str(uuid4()), on_event=events.append)
    assert result.status == "needs_input" and result.tool == "income_tax"
    assert "경비" in result.context
    assert "경비" in chat._failed_tool_answer(events)
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_selection_failure_is_not_reported_as_user_input_shortage(monkeypatch):
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=ValueError("malformed JSON")))
    events = []
    result = await planner.run_tools_for_query("종합소득세 계산해줘", user_id=str(uuid4()), on_event=events.append)
    assert result.status == "selection_error" and result.retryable
    assert "오류가 발생" in chat._failed_tool_answer(events)
    assert "필수 입력" not in chat._failed_tool_answer(events)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_chat_and_sse_continue_to_answer_for_general_tax_question(monkeypatch, stream):
    query = "부가가치세법 제39조의 매입세액 불공제 요건은?"
    monkeypatch.setattr(chat, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "prepare_context", AsyncMock(return_value=context_from_records([])))
    select = AsyncMock(return_value=None)
    monkeypatch.setattr(planner, "select_tool", select)
    verify = AsyncMock(return_value=("일반 분석 답변", {"status": "limited", "citations": []}))
    monkeypatch.setattr(chat, "_answer_evidence_context", verify)
    monkeypatch.setattr(chat, "_save_history", AsyncMock())
    if stream:
        events = [event async for event in chat.stream_chat_response(query, str(uuid4()), str(uuid4()))]
        assert any(event.get("text") == "일반 분석 답변" for event in events)
        assert not any(event.get("status") == "needs_input" for event in events)
    else:
        answer, _ = await chat.process_chat(query, str(uuid4()), str(uuid4()))
        assert answer == "일반 분석 답변"
    verify.assert_awaited_once()
    select.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,query", [
    ("calculation", "매입세액 공제 요건을 설명해줘"),
    ("document_search", "부가가치세 신고 시 첨부해야 하는 서류는?"),
    ("exact_lookup", "부가가치세법 제39조의 적용 요건을 설명해줘"),
])
async def test_model_plan_cannot_force_unrequested_tool(monkeypatch, kind, query):
    from app.services import question_planning
    from app.schemas.reliability import Issue, QuestionPlan
    invalid = QuestionPlan(issues=[Issue(id="I1", request_quote=query, law="부가가치세법", kind=kind, question=query)])
    monkeypatch.setattr(question_planning, "call_llm_structured", AsyncMock(return_value=invalid.model_dump()))
    plan = await question_planning.plan_question(query, ["부가가치세법"])
    assert plan.status == "fallback"
    assert all(issue.kind == "analysis" for issue in plan.issues)


@pytest.mark.asyncio
async def test_multiline_request_spans_are_verbatim_and_provider_compatible(monkeypatch):
    from app.services import question_planning
    query = '첫째 줄의 상황입니다.\n둘째 줄의 적용 요건을 설명해줘.'
    async def generate(messages, schema, **kwargs):
        spans = schema['$defs']['Issue']['properties']['request_quote']['enum']
        assert all(span in query and not any(c in span for c in '\n\r\t') for span in spans)
        return {'issues': [{'id': 'I1', 'request_quote': spans[-1], 'subject': '', 'law': 'ALL',
                            'kind': 'analysis', 'question': '적용 요건', 'depends_on': []}],
                'dates': [], 'assumptions': [], 'missing_inputs': [], 'status': 'planned'}
    monkeypatch.setattr(question_planning, 'call_llm_structured', generate)
    assert (await question_planning.plan_question(query, [])).status == 'planned'

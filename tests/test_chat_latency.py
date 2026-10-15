"""Steps that used to wait for each other without needing to (no model call)."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import Issue, QuestionPlan
from app.services import question_planning
from app.services import reliable_workflow as reliable
from app.services.evidence import context_from_records
from tests.test_reliability_workflow import source

PLAN = QuestionPlan(issues=[
    Issue(id="C1", kind="calculation", law="소득세법", request_quote="연봉 5천만원이면 소득세 얼마인지 계산하고",
          question="종합소득세 계산"),
    Issue(id="A1", kind="analysis", law="소득세법", request_quote="연말정산 절차도 설명해줘", question="연말정산 절차")])
QUERY = "연봉 5천만원이면 소득세 얼마인지 계산하고 연말정산 절차도 설명해줘"


@pytest.mark.asyncio
async def test_a_calculation_runs_while_the_evidence_search_is_still_going(monkeypatch):
    tool_started = asyncio.Event()

    async def retrieve(plan, *args, **kwargs):
        # The search only finishes once the calculation has started: sequential code would hang here.
        await asyncio.wait_for(tool_started.wait(), timeout=2)
        return context_from_records([], plan=plan)

    async def tool(query, **kwargs):
        tool_started.set()
        return None

    monkeypatch.setattr(reliable, "plan_question", AsyncMock(return_value=PLAN.model_copy(deep=True)))
    monkeypatch.setattr(reliable, "retrieve_issues", retrieve)
    monkeypatch.setattr(reliable, "attach_event_versions", AsyncMock(side_effect=lambda c: c))
    monkeypatch.setattr(reliable, "run_tools_for_query", tool)
    context = await reliable.prepare_context(QUERY, [], "u", [], AsyncMock())
    assert context.coverage["C1"]["error"] == "no_tool_needed"


@pytest.mark.asyncio
async def test_a_formula_that_cannot_be_released_becomes_analysis_only_after_the_search(monkeypatch):
    from app.services.calculator import formula_workflow
    from app.services.tools.executor import ToolRun
    seen = []

    async def retrieve(plan, *args, **kwargs):
        await asyncio.sleep(0.05)   # let the formula finish first
        seen.append([issue.kind for issue in plan.issues])
        return context_from_records([], plan=plan)

    monkeypatch.setattr(reliable, "plan_question", AsyncMock(return_value=PLAN.model_copy(deep=True)))
    monkeypatch.setattr(reliable, "retrieve_issues", retrieve)
    monkeypatch.setattr(reliable, "attach_event_versions", AsyncMock(side_effect=lambda c: c))
    monkeypatch.setattr(reliable, "run_tools_for_query",
                        AsyncMock(return_value=ToolRun("formula_calculation", "planned", "")))
    monkeypatch.setattr(formula_workflow, "calculate_reference", AsyncMock(return_value=("규칙 설명", None)))
    context = await reliable.prepare_context(QUERY, [], "u", [], AsyncMock())
    assert seen == [["calculation", "analysis"]]                      # the search read the plan unchanged
    assert [i.kind for i in context.plan.issues] == ["analysis", "analysis"]
    assert context.coverage["C1"]["error"] == "formula_not_verified"


@pytest.mark.asyncio
async def test_the_repair_search_skips_the_sufficiency_check(monkeypatch):
    monkeypatch.setattr(question_planning.config, "TAVILY_API_KEY", "")
    assess = AsyncMock(side_effect=AssertionError("no sufficiency check in the repair round"))
    monkeypatch.setattr(question_planning, "assess_issues", assess)
    plan = QuestionPlan(issues=[Issue(id="I1", request_quote="질문", law="소득세법", question="연말정산 절차")])
    search = AsyncMock(return_value=[source(law_name="소득세법")])
    context = await question_planning.retrieve_issues(plan, "질문", "u", search, assess=False)
    assert context.coverage["I1"]["status"] == "candidates" and context.coverage["I1"]["evidence_ids"]
    assert search.await_count == 1

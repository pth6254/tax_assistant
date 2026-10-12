"""Evidence the structure itself kept out of reach (2026-10-12 check; no model call)."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.schemas.law import LawArticleDetail
from app.schemas.reliability import Issue, QuestionPlan
from app.services import question_planning
from app.services.graph.index_service import article_key
from app.services.search import graph_search_service as graph
from app.services.search.hybrid_search_service import _cap_interpretations, _row_to_article_result
from tests.test_graph_rag import article
from tests.test_reliability_workflow import source

FRAMEWORK = '국세기본법 제47조의2 제6항 중복 적용'


def interpretation(number):
    return source(law_name='소득세법', article_no=f'24-02{number}', source_type='interpretation',
                  source_id=f'i{number}')


def test_interpretations_leave_room_for_the_articles_they_apply():
    rows = [interpretation(n) for n in range(4)] + [source(article_no=f'제{n}조', source_id=str(n)) for n in range(6)]
    kept = _cap_interpretations(rows, 8)
    assert len(kept) == 8 and sum(r.source_type == 'interpretation' for r in kept) == 2
    assert [r.article_no for r in kept[:2]] == ['24-020', '24-021']   # ranking order is kept


@pytest.mark.asyncio
async def test_graph_starts_from_the_top_statute_articles_below_interpretations(monkeypatch):
    monkeypatch.setattr(graph.config, 'GRAPH_RAG_ENABLED', True)
    seed = article(text='「시험법」 제2조에 따른다.')
    target = article('제2조', '제2조 본문')
    lookup = AsyncMock(side_effect=lambda law, number: LawArticleDetail(**(seed if number == '제1조' else target)))
    monkeypatch.setattr(graph, 'get_law_article', lookup)
    edge = dict(source_key=article_key(seed), target_key=article_key(target),
                law_name='시험법', article_no='제2조', evidence='「시험법」 제2조')
    monkeypatch.setattr(graph, 'neighbors', AsyncMock(return_value=[edge]))
    leaders = [replace(_row_to_article_result(article(f'제9{n}조') | {'similarity_score': 1}),
                       source_type='interpretation') for n in range(3)]
    results = [*leaders, _row_to_article_result(seed | {'similarity_score': 1})]
    expanded = await graph.expand_graph(results)
    assert [r.article_no for r in expanded[len(results):]] == ['제2조']


def retrieval(monkeypatch, missing):
    monkeypatch.setattr(question_planning.config, 'TAVILY_API_KEY', '')
    search = AsyncMock(side_effect=lambda queries, law, **kwargs: [
        source(law_name=law, article_no='제47조의2' if law == '국세기본법' else '제81조의5', source_id=law)])
    rounds = []

    async def assess(issues, records, scope_issues=None):
        rounds.append(1)
        return {i.id: {'status': 'missing' if len(rounds) == 1 else 'sufficient',
                       'missing_requirements': missing if len(rounds) == 1 else [],
                       'relevant_ids': [r.id for r in records[i.id]]} for i in issues}
    monkeypatch.setattr(question_planning, 'assess_issues', assess)
    return search


@pytest.mark.asyncio
async def test_every_gap_is_searched_and_a_named_article_is_looked_up_by_itself(monkeypatch):
    search = retrieval(monkeypatch, ['장부 기록 의무', '추계 신고', FRAMEWORK])
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='질문', law='소득세법', question='복식부기 장부 요건')])
    await question_planning.retrieve_issues(plan, '질문', 'user', search)
    queries, law = search.call_args_list[-1].args
    assert law == '소득세법' and len(queries) == 4
    assert queries[-1] == '국세기본법 제47조의2'   # the third gap was dropped before


@pytest.mark.asyncio
async def test_a_penalty_issue_under_a_tax_law_also_searches_the_framework_act(monkeypatch):
    search = retrieval(monkeypatch, [])
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='무기장가산세와 신고불성실가산세는 중복되나요?',
                                      law='소득세법', question='무기장가산세 신고불성실가산세 중복')])
    result = await question_planning.retrieve_issues(plan, '질문', 'user', search)
    assert [call.args[1] for call in search.call_args_list] == ['소득세법', '국세기본법']
    assert {r.law_name for r in result.records} == {'소득세법', '국세기본법'}
    assert len(result.coverage['I1']['evidence_ids']) == 2


@pytest.mark.asyncio
async def test_other_issues_search_only_their_own_law(monkeypatch):
    search = retrieval(monkeypatch, [])
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='1세대 1주택 비과세 요건', law='소득세법',
                                      question='1세대 1주택 비과세 요건')])
    await question_planning.retrieve_issues(plan, '질문', 'user', search)
    assert [call.args[1] for call in search.call_args_list] == ['소득세법']


@pytest.mark.asyncio
async def test_a_plan_with_its_own_framework_act_issue_needs_no_extra_search(monkeypatch):
    search = retrieval(monkeypatch, [])
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='무기장가산세', law='소득세법', question='무기장가산세'),
                                Issue(id='I2', request_quote='중복', law='국세기본법', question='가산세 중복 적용')])
    await question_planning.retrieve_issues(plan, '질문', 'user', search)
    assert sorted(call.args[1] for call in search.call_args_list) == ['국세기본법', '소득세법']

"""An article another statute is named for is looked up exactly, not filtered away."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import ClaimJudgment, Issue, JudgeReport, QuestionPlan
from app.services import reliable_workflow as workflow
from app.services.evidence import context_from_records
from app.services.search.hybrid_search_service import _direct_in_scope, _names_law

GAP = '소득세법 제81조의5 장부기록 불성실 가산세의 적용 요건·산정 방식·적용 제외'


def row(law_name):
    return SimpleNamespace(law_name=law_name)


def test_named_statute_survives_an_issue_filter_for_another_law():
    assert _names_law('소득세법 제81조의5') and not _names_law('제81조의5')
    assert _direct_in_scope(row('소득세법'), '국세기본법', '소득세법 제81조의5')
    # An unnamed article never leaks in from another law, and the filters still hold.
    assert not _direct_in_scope(row('소득세법'), '국세기본법', '제81조의5')
    assert _direct_in_scope(row('국세기본법'), '국세기본법', '제47조의2')
    assert _direct_in_scope(row('소득세법 시행령'), '소득세법', '제10조')
    assert _direct_in_scope(row('소득세법'), 'ALL', '제81조의5')


def issue_and_context(requirements, law='국세기본법'):
    issue = Issue(id='1', request_quote='질문', law=law, question='가산세 중복 적용')
    coverage = {'1': {'status': 'missing', 'attempts': 1, 'error': None, 'evidence_ids': [],
                      'missing_requirements': requirements}}
    return issue, context_from_records([], plan=QuestionPlan(issues=[issue]), coverage=coverage)


def judge(reason):
    return JudgeReport(claims=[ClaimJudgment(claim_id='1:1-1', support='insufficient', applicability='supported',
                                             evidence_ids=[], reason=reason)], missing_issue_ids=['1'])


def test_only_articles_named_with_a_known_statute_become_queries():
    issue, ctx = issue_and_context([GAP, '관련 소득세법 시행령의 구체적 요건·예외',
                                    '없는법 제3조의 요건', '제115조의 요건'])
    refs = workflow.gap_references(issue, ctx, judge('소득세법 제81조의5·제115조의 적용 대상이 없습니다.'))
    assert refs == ['소득세법 제81조의5']  # no article, unknown statute, or bare number is searched


def test_references_from_other_issues_and_excess_are_ignored():
    issue, ctx = issue_and_context([f'소득세법 제{n}조 요건' for n in range(1, 8)])
    other = JudgeReport(claims=[ClaimJudgment(claim_id='2:1', support='insufficient', applicability='supported',
                                              evidence_ids=[], reason='법인세법 제99조가 없습니다.')])
    refs = workflow.gap_references(issue, ctx, other)
    assert len(refs) == workflow.MAX_GAP_REFERENCES and all(r.startswith('소득세법 제') for r in refs)
    assert '법인세법 제99조' not in refs


@pytest.mark.asyncio
async def test_repair_search_names_the_missing_article(monkeypatch):
    issue, ctx = issue_and_context([GAP])
    seen = {}

    async def generate(query, context, *, repair, on_progress):
        seen['repair'] = repair
        return 'answer', {}

    async def retrieve(plan, query, user_id, search, on_progress=None, scope_issues=None):
        seen["scope"] = scope_issues
        seen['plan'] = plan
        return context_from_records([], plan=plan, coverage=ctx.coverage)

    monkeypatch.setattr(workflow, 'generate_verified_answer', generate)
    monkeypatch.setattr(workflow, 'retrieve_issues', retrieve)
    monkeypatch.setattr(workflow, 'call_llm_structured', AsyncMock(side_effect=ValueError('no refinement')))
    await workflow.answer_context('질문', ctx, 'user', search=None)
    await seen['repair']({'1'}, None)
    question = seen['plan'].issues[0].question
    assert '소득세법 제81조의5' in question and question.startswith('가산세 중복 적용')
    assert seen['plan'].issues[0].law == '국세기본법'  # the issue itself keeps its law


def test_gap_articles_are_read_even_when_a_word_precedes_the_statute_name():
    # Judges write "관련 소득세법 제81조의5(…)" more often than a bare "소득세법 제81조의5".
    issue, ctx = issue_and_context(['관련 소득세법 제81조의5(무기장가산세) 전문 및 복식부기의무자 요건',
                                    '위 규정이 준용하는 국세기본법 제47조의2 제6항의 범위'])
    refs = workflow.gap_references(issue, ctx, judge('그리고 상속세 및 증여세법 제53조도 필요합니다.'))
    assert refs == ['소득세법 제81조의5', '국세기본법 제47조의2', '상속세 및 증여세법 제53조']

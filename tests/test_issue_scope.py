"""Each issue is judged on its own law's evidence, plus articles it names with their statute."""
import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import Issue, QuestionPlan
from app.services import issue_coverage, question_planning
from app.services.evidence import record_from_result
from tests.test_reliability_workflow import source


def record(law, article):
    return record_from_result(source(law_name=law, article_no=article, source_id=f'{law}-{article}'))


def issue(key, law, question):
    return Issue(id=key, request_quote='질문', law=law, question=question)


def judge_llm(captured, status='sufficient', missing=()):
    """Stands in for the coverage Judge; records what it was shown."""
    async def call(messages, schema, **kwargs):
        payload = json.loads(messages[1]['content'])[0]
        captured.append({'payload': payload, 'system': messages[0]['content']})
        ids = [row['id'] for row in payload['evidence']]
        return {'issues': [{'issue_id': payload['issue_id'], 'status': status if ids else 'insufficient',
                            'relevant_evidence_ids': ids[:1], 'missing_requirements': list(missing)}]}
    return AsyncMock(side_effect=call)


def test_only_articles_named_with_their_statute_cross_the_law_boundary():
    own, named, unnamed = record('소득세법', '제81조의5'), record('국세기본법', '제47조의2'), record('국세기본법', '제47조의3')
    asked = issue('1', '소득세법', '장부 기록 가산세와 국세기본법 제47조의2 제6항의 관계')
    assert issue_coverage._matching_law(asked, own)
    assert issue_coverage._matching_law(asked, named)
    assert not issue_coverage._matching_law(asked, unnamed)  # same statute, but never asked for
    assert not issue_coverage._matching_law(issue('1', '소득세법', '장부 기록 가산세'), named)
    assert issue_coverage._matching_law(issue('1', 'ALL', '질문'), unnamed)


@pytest.mark.asyncio
async def test_judge_sees_named_cross_law_article_and_the_other_issues(monkeypatch):
    shown = []
    monkeypatch.setattr(issue_coverage, 'call_llm_structured', judge_llm(shown))
    first = issue('1', '소득세법', '무기장가산세 요건과 국세기본법 제47조의2')
    second = issue('2', '국세기본법', '가산세 중복 적용 조정')
    records = {'1': [record('소득세법', '제81조의5'), record('국세기본법', '제47조의2'), record('국세기본법', '제47조의3')]}
    await issue_coverage.assess_issues([first], records, scope_issues=[first, second])
    payload = shown[0]['payload']
    assert {row['reference'] for row in payload['evidence']} == {'제81조의5', '제47조의2'}
    assert payload['other_issues'] == [{'issue_id': '2', 'subject': '', 'law': '국세기본법'}]
    assert 'other_issues' in shown[0]['system'] and '요구하지 마세요' in shown[0]['system']


@pytest.mark.asyncio
async def test_retry_assessment_sees_the_article_the_first_assessment_asked_for(monkeypatch):
    """The first Judge asked for another statute's article; fetching it must not be wasted."""
    monkeypatch.setattr(question_planning.config, 'TAVILY_API_KEY', '')
    shown = []
    base = judge_llm(shown)
    gap = '국세기본법 제47조의2 제6항 중복 적용 제한'

    async def call(messages, schema, **kwargs):
        first_round = not shown
        result = await base(messages, schema, **kwargs)
        if first_round:
            result['issues'][0].update(status='insufficient', missing_requirements=[gap])
        return result

    monkeypatch.setattr(issue_coverage, 'call_llm_structured', AsyncMock(side_effect=call))
    own, cross = source(law_name='소득세법', article_no='제81조의5', source_id='a'), source(
        law_name='국세기본법', article_no='제47조의2', source_id='b')
    search = AsyncMock(side_effect=[[own], [cross]])
    first, second = issue('1', '소득세법', '무기장가산세 요건'), issue('2', '국세기본법', '중복 조정')
    # A repair retries only the unresolved issue but still tells the Judge who owns the rest.
    result = await question_planning.retrieve_issues(
        QuestionPlan(issues=[first]), '질문', 'user', search, scope_issues=[first, second])
    second_round = [item['payload'] for item in shown if item['payload']['issue_id'] == '1'][-1]
    assert '제47조의2' in {row['reference'] for row in second_round['evidence']}
    assert second_round['other_issues'] == [{'issue_id': '2', 'subject': '', 'law': '국세기본법'}]
    assert result.coverage['1']['status'] == 'sufficient' and result.coverage['1']['attempts'] == 2

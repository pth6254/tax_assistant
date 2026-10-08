"""Headings, repetition diagnostics and the generation input for multi-issue answers."""
import json

import pytest

from app.schemas.reliability import AnswerClaim, Issue, QuestionPlan
from app.services import claim_verification as claims
from app.services.evidence import context_from_records
from tests.test_reliability_workflow import context as single_context
from tests.test_scoped_answers import two_issues, wire_claim

# Sentences from a real answer: the second restates the first in other words.
CONCLUSION = ('무기장가산세와 신고불성실가산세가 동시에 적용되는 경우에는 원칙적으로 두 가산세액을 모두 더하지 않고, '
              '금액이 큰 가산세만 적용합니다. 두 금액이 같으면 무신고가산세 또는 과소신고·초과환급신고가산세를 적용합니다.')
RESTATED = ('과소신고·초과환급신고가산세에도 위 조정 규정이 준용됩니다. 따라서 장부 기록·보관 불성실 가산세와 '
            '과소신고·초과환급신고가산세가 함께 적용되는 경우에도 큰 가산세액만 적용하며, 금액이 같으면 '
            '과소신고·초과환급신고가산세를 적용합니다.')
OTHER_TOPIC = ('사업자가 장부를 비치·기록하지 않았거나 장부에 따른 소득금액이 기장해야 할 금액에 미달하면 '
               '해당 과세기간 종합소득 결정세액에 가산세를 더합니다.')


def plan(*pairs):
    return QuestionPlan(issues=[Issue(id=str(n), request_quote='질문', subject=subject, law=law, question='질문')
                                for n, (subject, law) in enumerate(pairs, 1)])


def test_common_subject_only_when_several_issues_share_one():
    assert claims.common_subject(plan(('복식부기의무자', '소득세법'), ('복식부기의무자', '국세기본법'))) == '복식부기의무자'
    assert claims.common_subject(plan(('A', '법인세법'), ('B', '법인세법'))) == ''
    assert claims.common_subject(plan(('복식부기의무자', '소득세법'))) == ''
    assert claims.common_subject(plan(('', '소득세법'), ('', '국세기본법'))) == ''


def released(issue_id, key, text):
    return AnswerClaim(id=key, issue_id=issue_id, text=text, kind='fact', presentation_role='explanation')


def headings(answer):
    return [line for line in answer.splitlines() if line.startswith('#')]


def test_headings_drop_a_subject_every_issue_shares_but_keep_distinct_ones():
    base = single_context()
    same = context_from_records(base.records, plan=plan(('복식부기의무자', '소득세법'), ('복식부기의무자', '국세기본법')))
    rows = [released('1', '1:1', OTHER_TOPIC), released('2', '2:1', CONCLUSION)]
    text = '\n'.join(headings(claims.render_structured_answer(rows, same, '질문')))
    assert '복식부기의무자' not in text and '소득세' in text and '국세기본법' in text
    distinct = context_from_records(base.records, plan=plan(('A', '법인세법'), ('B', '법인세법')))
    text = '\n'.join(headings(claims.render_structured_answer(rows, distinct, 'A회사는 B회사에게')))
    assert 'A회사' in text and 'B회사' in text


def test_repeat_diagnostics_flag_restated_conclusions_and_repeated_conditions_without_dropping_anything():
    first, second, other = (released('2', '2a', CONCLUSION), released('2', '2b', RESTATED),
                            released('1', '1a', OTHER_TOPIC))
    first.conditions = ['소득세법상 장부 기록·보관 불성실 가산세와 국세기본법상 무신고가산세 또는 과소신고·초과환급신고가산세가 동시에 적용되는 경우입니다.']
    second.conditions = ['소득세법상 장부 기록·보관 불성실 가산세와 국세기본법상 과소신고·초과환급신고가산세가 동시에 적용되는 경우입니다.']
    other.conditions = ['대통령령으로 정하는 소규모사업자는 제외됩니다.']
    result = claims.repeat_diagnostics([first, second, other])
    assert [row['claims'] for row in result['text']] == [['2a', '2b']]
    assert [row['claims'] for row in result['conditions']] == [['2a', '2b']]
    assert result['conditions'][0]['similarity'] >= 0.8
    assert (first.text, second.text, other.text) == (CONCLUSION, RESTATED, OTHER_TOPIC)  # diagnostic only
    assert claims.repeat_diagnostics([first, other]) == {'text': [], 'conditions': []}


@pytest.mark.asyncio
async def test_generation_is_told_what_the_other_issues_own(monkeypatch):
    ctx = two_issues()
    sent = []

    async def generate(messages, schema, **kwargs):
        sent.append(messages)
        return wire_claim('I1')

    async def judge(query, draft, context):
        return None, 'skipped'

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    await claims.generate_issue('질문', ctx.plan.issues[0], ctx)
    payload = json.loads(sent[0][1]['content'])
    assert payload['other_issues'] == [{'id': 'I2', 'subject': '', 'law': '부가가치세법',
                                        'question': ctx.plan.issues[1].question}]
    system = sent[0][0]['content']
    assert 'other_issues는 같은 질문의 다른 쟁점' in system and '되풀이하면 새 주장이 아닙니다' in system


def test_planner_generation_and_judge_share_one_rule_for_applying_the_users_facts():
    """Prompt contracts only: whether the model follows them needs a live run."""
    import inspect
    from app.services import question_planning
    planner = inspect.getsource(question_planning.plan_question)
    assert '질문의 사실관계에 대한 적용' in planner
    scoped = claims.SCOPED_GENERATION_PROMPT
    assert '질문에 나온 사실에 적용한 주장을 따로 쓰세요' in scoped
    assert '질문에 없는 사실을 지어내거나 확정하지 마세요' in scoped
    assert '일반적인 조건부 설명으로 한정하세요' not in scoped  # no longer forbids the application
    assert '질문에 실제로 적힌 사실만 전제로' in claims.JUDGE_PROMPT
    assert 'applicability는 contradicted' in claims.JUDGE_PROMPT

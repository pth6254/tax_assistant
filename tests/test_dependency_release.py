"""A premise withheld for notation only no longer erases independently checked claims."""
import json

import pytest

from app.schemas.reliability import AnswerClaim, AnswerDraft, ClaimCitation, ClaimJudgment, JudgeReport
from app.services import claim_verification as claims
from tests.test_reliability_workflow import context
from tests.test_scoped_answers import two_issues, wire_claim


def chain(ctx):
    cite = [ClaimCitation(evidence_id=ctx.records[0].id, quote='조건을 충족한 경우에만 적용한다.')]
    return AnswerDraft(claims=[
        AnswerClaim(id='C1', issue_id='I1', kind='legal', text='전제 판단입니다.', citations=cite),
        AnswerClaim(id='C2', issue_id='I1', kind='legal', text='전제를 조건으로 한 공제율 설명입니다.',
                    citations=cite, depends_on=['C1'], conditions=['제외 자산이 아니어야 합니다.']),
        AnswerClaim(id='C3', issue_id='I1', kind='legal', text='그 공제율에 따른 계산 순서입니다.',
                    citations=cite, depends_on=['C2'])])


def judged(value, **verdicts):
    return JudgeReport(claims=[ClaimJudgment(
        claim_id=c.id, support=verdicts.get(c.id, 'supported'), applicability=verdicts.get(c.id, 'supported'),
        evidence_ids=[e.evidence_id for e in c.citations], reason='근거와 일치') for c in value.claims])


def release(value, premise_errors, judge):
    checks = {c.id: [] for c in value.claims}
    checks['C1'] = premise_errors
    return claims.release_claims(value, checks, judge, context().plan, mode='enforce')


def test_notation_only_premise_failure_releases_checked_dependents_transitively():
    value = chain(context())
    released, rejected = release(value, ['prose_reference_mismatch', 'prose_reference_mismatch'], judged(value))
    assert [c.id for c in released] == ['C2', 'C3']
    assert rejected == {'C1': ['prose_reference_mismatch', 'prose_reference_mismatch']}


@pytest.mark.parametrize('premise_errors, verdicts', [
    (['prose_reference_mismatch'], {'C1': 'insufficient'}),        # content not supported
    (['invalid_quote_or_evidence'], {}),                            # integrity failure
    (['prose_reference_mismatch', 'missing_evidence'], {}),         # a blocking non-notation failure
    (['historical_version_required'], {}),                          # needs another version
])
def test_other_premise_failures_still_cascade(premise_errors, verdicts):
    value = chain(context())
    released, rejected = release(value, premise_errors, judged(value, **verdicts))
    assert released == []
    assert rejected['C2'] == rejected['C3'] == ['dependency_withheld']


def test_dependent_must_pass_its_own_checks_and_judge():
    value = chain(context())
    released, rejected = release(value, ['prose_reference_mismatch'], judged(value, C2='insufficient'))
    assert released == [] and 'semantic_check_not_passed' in rejected['C2']


def test_detached_claim_is_marked_where_shown():
    value = chain(context())
    released, _ = release(value, ['prose_reference_mismatch'], judged(value))
    for answer in (claims.render_claims(released, context()),
                   claims.render_structured_answer(released, context())):
        assert '전제를 조건으로 한 공제율 설명입니다.' in answer
        assert answer.count(claims.DETACHED_NOTE) == 1  # Only C2 lost its premise; C3's is shown.
        assert '전제 판단입니다.' not in answer


@pytest.mark.asyncio
async def test_report_records_which_premise_a_released_claim_was_detached_from(monkeypatch):
    ctx = two_issues()

    async def generate(messages, schema, **kwargs):
        key = json.loads(messages[1]['content'])['plan']['issues'][0]['id']
        value = wire_claim(key, '제9조에 따라 적용합니다.' if key == 'I1' else '두 번째 요건을 충족하면 적용합니다.')
        if key == 'I1':
            value['claims'].append({'id': 'C2', 'issue_id': key, 'text': '조건을 충족하면 적용합니다.', 'kind': 'legal',
                                    'citations': [{'evidence_id': 'E1', 'quote': 'E1:P2'}],
                                    'conditions': [], 'depends_on': ['C1']})
        return value

    async def judge(query, draft, context):
        return judged(draft), None

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx)
    entries = {c['id']: c for c in report['claims']}
    assert entries['I1:C1']['released'] is False
    assert entries['I1:C2']['released'] is True and entries['I1:C2']['detached_from'] == ['I1:C1']
    assert 'detached_from' not in entries['I2:C1']
    assert claims.DETACHED_NOTE in answer and '제9조' not in answer

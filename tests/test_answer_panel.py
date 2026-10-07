"""What the evidence panel stores must agree with what the answer itself says."""
import pytest

from app.schemas.reliability import AnswerClaim
from app.services import claim_verification as claims
from tests.test_scoped_answers import supported, two_issues, wire_claim


def summary_claim(issue_id, text):
    value = wire_claim(issue_id, text)
    value['claims'][0]['kind'] = 'source_summary'
    return value


@pytest.mark.asyncio
async def test_released_source_summaries_get_a_matching_note_and_no_date_prompt(monkeypatch):
    ctx = two_issues()
    ctx.plan.missing_inputs = [claims.DATE_INPUT]

    async def generate(messages, schema, **kwargs):
        import json
        key = json.loads(messages[1]['content'])['plan']['issues'][0]['id']
        return summary_claim(key, f'{key}번 쟁점의 원문 기준을 설명합니다.')

    async def judge(query, draft, context):
        return supported(draft), None

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx)
    assert report['status'] == 'checked' and report['metrics']['claims_released'] == 2
    # Two released explanations must not be reported as "no legal explanation passed".
    assert '통과한 법적 설명이 없습니다' not in report['note']
    assert '확보한 법령 원문의 설명과 인용을 대조했습니다' in report['note']
    # The answer already says it rests on the retrieved text, so the panel does not ask for a date again.
    assert report['plan']['missing_inputs'] == []
    assert claims.DATE_INPUT not in answer


def claim(kind, conditions=()):
    return AnswerClaim(id='C1', issue_id='I1', text='설명입니다.', kind=kind, conditions=list(conditions))


def test_date_prompt_stays_only_when_the_answer_never_states_a_general_scope():
    ctx = two_issues()
    ctx.plan.missing_inputs = [claims.DATE_INPUT, '과거 증여 내역']
    assert claims.requested_inputs(ctx, []) == ['과거 증여 내역']
    assert claims.requested_inputs(ctx, [claim('legal')]) == [claims.DATE_INPUT, '과거 증여 내역']
    assert claims.requested_inputs(ctx, [claim('source_summary')]) == ['과거 증여 내역']
    assert claims.requested_inputs(ctx, [claim('legal', [claims.UNSPECIFIED_SCOPE])]) == ['과거 증여 내역']

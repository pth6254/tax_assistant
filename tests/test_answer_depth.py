"""Answer depth: no claim-count cap, consequences planned, cited passages shown (no model call)."""
import inspect

import pytest

from app.schemas.reliability import AnswerClaim, AnswerDraft, ClaimCitation
from app.services import claim_verification as claims
from app.services import question_planning
from app.services.evidence import record_from_result
from tests.test_reliability_workflow import source
from tests.test_scoped_answers import two_issues, wire_claim


@pytest.mark.asyncio
async def test_an_issue_may_release_as_many_claims_as_its_evidence_supports(monkeypatch):
    ctx = two_issues()
    seen = {}

    async def generate(messages, schema, **kwargs):
        seen.update(schema=schema, max_tokens=kwargs['max_tokens'])
        many = wire_claim('I1')['claims'] * 9
        return {'claims': [dict(claim, id=f'C{n}', text=f'조건 {n}을 충족하면 적용합니다.') for n, claim in enumerate(many)]}

    async def judge(query, draft, context):
        return None, 'skipped'

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    draft, *_ = await claims.generate_issue('질문', ctx.plan.issues[0], ctx)
    assert len(draft.claims) == 9
    assert 'maxItems' not in seen['schema']['properties']['claims']
    assert seen['max_tokens'] == claims.GENERATION_MAX_TOKENS
    assert '최대 5개' not in claims.SCOPED_GENERATION_PROMPT and '간결하게' not in claims.GENERATION_PROMPT
    assert '세무 효과' in claims.SCOPED_GENERATION_PROMPT and '사후 조치' in claims.SCOPED_GENERATION_PROMPT
    AnswerDraft(claims=[AnswerClaim(id=f'C{n}', issue_id='I1', text='a', kind='fact') for n in range(40)])


def test_the_planner_adds_the_taxes_that_follow_from_the_treatment():
    """Prompt contract only; whether the model follows it needs a live run."""
    planner = inspect.getsource(question_planning.plan_question)
    assert '바로 따라오는 다른 세목' in planner and '최대 2개' in planner


def test_the_panel_receives_the_exact_passages_each_source_backs():
    text = '제1조\n① 첫째 요건을 충족해야 한다.\n② 둘째 예외를 둔다.'
    record = record_from_result(source(content=text, original_text=text)).model_copy(update={'version_id': 'v1'})
    copy = record_from_result(source(content=text, original_text=text, source_id='17-copy')).model_copy(
        update={'version_id': 'v1'})   # the same stored row reached by another path
    released = [AnswerClaim(id='C2', issue_id='I1', text='예외', kind='legal',
                            citations=[ClaimCitation(evidence_id=copy.id, quote='② 둘째 예외를 둔다.')]),
                AnswerClaim(id='C1', issue_id='I1', text='요건', kind='legal',
                            citations=[ClaimCitation(evidence_id=record.id, quote='① 첫째 요건을 충족해야 한다.')])]
    quotes = claims.cited_passages(record, released, [record, copy])
    assert quotes == ['① 첫째 요건을 충족해야 한다.', '② 둘째 예외를 둔다.']   # text order, both copies
    assert claims.cited_passages(record, [], [record]) == []


@pytest.mark.asyncio
async def test_claims_that_passed_are_shown_before_a_repair_round(monkeypatch):
    from tests.test_scoped_answers import supported
    ctx = two_issues()
    events = []

    async def generate(messages, schema, **kwargs):
        return wire_claim(__import__('json').loads(messages[1]['content'])['plan']['issues'][0]['id'])

    async def judge(query, draft, context):
        return (supported(draft), None) if context.plan.issues[0].id == 'I1' else (None, 'TimeoutError')

    async def repair(missing, report):
        return ctx

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx, repair=repair, on_progress=events.append)
    kinds = [e.get('status') or e['type'] for e in events]
    retry = len(kinds) - 1 - kinds[::-1].index('generating')   # I2 is generated again after the preview
    assert kinds.index('repairing') < kinds.index('draft') < retry
    draft = next(e for e in events if e['type'] == 'draft')['text']
    assert '조건을 충족하면' in draft and '조건을 충족하면' in answer   # the final answer keeps what was shown


@pytest.mark.asyncio
async def test_no_preview_when_nothing_passed(monkeypatch):
    ctx = two_issues()
    events = []

    async def judge(query, draft, context):
        return None, 'TimeoutError'

    monkeypatch.setattr(claims, 'call_llm_structured', lambda *a, **k: __import__('asyncio').sleep(0, wire_claim('I1')))
    monkeypatch.setattr(claims, 'judge_claims', judge)
    await claims.generate_verified_answer('질문', ctx, repair=lambda *a: __import__('asyncio').sleep(0, ctx),
                                          on_progress=events.append)
    assert 'draft' not in [e['type'] for e in events]

"""Deterministic checks withhold; word-based guesses are verified by the Judge."""
import inspect
import json
import re
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import AnswerDraft, ClaimJudgment, JudgeReport
from app.services import claim_verification as claims
from app.services.evidence import context_from_records, digest, record_from_result
from tests.test_reliability_workflow import context, draft, source
from tests.test_scoped_answers import two_issues, wire_claim


def verdict(value, result='supported'):
    return JudgeReport(claims=[ClaimJudgment(claim_id=c.id, support=result, applicability=result,
                                             evidence_ids=[e.evidence_id for e in c.citations], reason='대조')
                               for c in value.claims])


def test_every_emitted_code_has_one_registered_gate():
    text = inspect.getsource(claims)
    emitted = set(re.findall(r'errors\.append\("([a-z_]+)"\)', text))
    emitted |= set(re.findall(r'(?:reasons\.append|rejected\[claim\.id\] =)\(?\[?"([a-z_]+)"', text))
    emitted |= {'prose_reference_mismatch'}
    assert emitted <= set(claims.CHECKS), emitted - set(claims.CHECKS)
    assert {check.gate for check in claims.CHECKS.values()} == {'block', 'signal'}
    # Only word-based guesses are signals; facts about quotes, sources, articles,
    # amounts and dates keep withholding on their own.
    assert claims.SIGNAL_CHECKS == {'tax_scope_mismatch', 'subject_scope_mismatch',
                                    'source_scope_unstated', 'historical_scope_unstated'}


def scoped_claim():
    ctx = context()
    ctx.plan.issues[0].law = '부가가치세법'
    value = draft(ctx, '이 비용은 법인세 손금 여부도 함께 검토합니다.')
    return ctx, value


def test_signal_alone_is_left_to_the_judge(monkeypatch):
    ctx, value = scoped_claim()
    checked = claims.check_claims(value, ctx, '질문')
    assert checked['C1'] == ['tax_scope_mismatch']
    released, _ = claims.release_claims(value, checked, verdict(value), ctx.plan, mode='enforce')
    assert [c.id for c in released] == ['C1']
    released, rejected = claims.release_claims(value, checked, verdict(value, 'insufficient'), ctx.plan, mode='enforce')
    assert not released and rejected['C1'] == ['semantic_check_not_passed']
    monkeypatch.setattr(claims.config, 'CLAIM_SIGNAL_GATE', 'block')
    released, rejected = claims.release_claims(value, checked, verdict(value), ctx.plan, mode='enforce')
    assert not released and rejected['C1'] == ['tax_scope_mismatch']


def test_blocking_codes_still_withhold_a_supported_claim():
    ctx = context()
    value = draft(ctx, '시험법 제99조에 따라 적용합니다.')
    checked = claims.check_claims(value, ctx, '질문')
    _, rejected = claims.release_claims(value, checked, verdict(value), ctx.plan, mode='enforce')
    assert rejected['C1'] == ['prose_reference_mismatch']


@pytest.mark.asyncio
async def test_judge_is_shown_the_signal_points(monkeypatch):
    ctx, value = scoped_claim()
    llm = AsyncMock(return_value={'claims': [dict(claim_id='C1', support='supported', applicability='supported',
                                                  evidence_ids=['E1'], reason='비교 언급')], 'missing_issue_ids': []})
    monkeypatch.setattr(claims, 'call_llm_structured', llm)
    await claims.judge_claims('질문', value, ctx)
    payload = json.loads(llm.call_args.args[0][1]['content'])
    assert payload['server_flags'] == {'C1': [{'code': 'tax_scope_mismatch', 'category': 'repairable',
                                               'detail': ['부가가치세법'], 'fix': claims.FIX_HINTS['tax_scope_mismatch']}]}
    assert 'server_flags' in llm.call_args.args[0][0]['content']


def test_reference_handles_are_written_by_the_server():
    ctx = two_issues()
    _, sources, spans = claims.source_units(ctx)
    value = AnswerDraft.model_validate(wire_claim('I1', '[[E1]] 제1항에 따라 조건을 충족하면 적용합니다.'))
    value.claims[0].conditions = ['[[E1]]의 요건을 확인하세요.']
    claims.expand_citations(value, sources, spans, 'I1')
    assert value.claims[0].text == '법인세법 제1조 제1항에 따라 조건을 충족하면 적용합니다.'
    assert value.claims[0].conditions == ['법인세법 제1조의 요건을 확인하세요.']
    assert claims.check_claims(value, ctx, '질문')['C1'] == []


def test_handle_of_an_uncited_source_withholds_the_claim():
    ctx = two_issues()
    _, sources, spans = claims.source_units(ctx)
    value = AnswerDraft.model_validate(wire_claim('I1', '[[E2]]에 따라 적용합니다.'))
    claims.expand_citations(value, sources, spans, 'I1')
    assert '[[E2]]' in value.claims[0].text
    assert 'unresolved_reference_placeholder' in claims.check_claims(value, ctx, '질문')['C1']


def test_amount_may_come_from_the_cited_text_but_not_from_nowhere():
    text = '제1조\n① 이자소득의 합계액이 2천만원 이하이면 합산하지 않는다.\n② 조건을 충족한 경우에만 적용한다.'
    record = record_from_result(source(content=text, original_text=text, content_hash=digest(text)))
    ctx = context_from_records([record], plan=context().plan)
    grounded = draft(ctx, '합계액이 2천만원 이하이면 세액 계산에서 합산하지 않습니다.')
    grounded.claims[0].citations[0].evidence_id = record.id
    assert claims.check_claims(grounded, ctx, '질문')['C1'] == []
    invented = grounded.model_copy(deep=True)
    invented.claims[0].text = '납부세액은 300만원입니다.'
    assert 'generated_tax_amount_without_calculator' in claims.check_claims(invented, ctx, '질문')['C1']

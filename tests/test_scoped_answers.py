"""Failures stay within their issue; released text keeps exact source bindings."""
import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import AnswerDraft, ClaimJudgment, JudgeReport, Issue, QuestionPlan
from app.services import claim_verification as claims, issue_coverage
from app.services.evidence import context_from_records, record_from_result
from app.services.tools import planner, policy
from app.services.answer_verification import unavailable_verification
from tests.test_reliability_workflow import source


def two_issues():
    records = [record_from_result(source(law_name='법인세법')),
               record_from_result(source(law_name='부가가치세법', source_id='18'))]
    plan = QuestionPlan(issues=[Issue(id=f'I{n}', request_quote='질문', law=r.law_name,
                                     question=r.law_name + ' 적용 요건') for n, r in enumerate(records, 1)])
    coverage = {f'I{n}': {'status': 'sufficient', 'evidence_ids': [r.id], 'relevant_ids': [r.id]}
                for n, r in enumerate(records, 1)}
    return context_from_records(records, plan=plan, coverage=coverage)


def wire_claim(issue_id, text='조건을 충족하면 적용합니다.'):
    return {'claims': [{'id': 'C1', 'issue_id': issue_id, 'text': text, 'kind': 'legal',
                        'citations': [{'evidence_id': 'E1', 'quote': 'E1:P2'}],
                        'conditions': [], 'depends_on': []}]}


def supported(draft):
    return JudgeReport(claims=[ClaimJudgment(claim_id=c.id, support='supported', applicability='supported',
                       evidence_ids=[e.evidence_id for e in c.citations], reason='요건과 원문 일치') for c in draft.claims])


@pytest.mark.asyncio
async def test_failed_judge_does_not_withhold_an_independent_issue(monkeypatch):
    ctx = two_issues()

    async def generate(messages, schema, **kwargs):
        data = json.loads(messages[1]['content'])
        issue = data['plan']['issues'][0]
        assert len(data['plan']['issues']) == len(data['evidence']) == 1
        assert data['evidence'][0]['law_name'] == issue['law']
        return wire_claim(issue['id'])

    async def judge(query, draft, context):
        if context.plan.issues[0].id == 'I2':
            return None, 'TimeoutError'
        return supported(draft), None

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx)
    assert report['status'] == 'limited'
    assert {c['issue_id'] for c in report['claims'] if c['released']} == {'I1'}
    assert report['metrics']['issues_answered'] == 1
    assert report['citations'][0]['evidence_id'] == ctx.records[0].id
    assert '조건을 충족하면' in answer and '판단을 보류' in answer


def test_source_span_cannot_be_bound_to_a_different_original():
    ctx = two_issues()
    _, sources, spans = claims.source_units(ctx)
    value = AnswerDraft.model_validate(wire_claim('I1'))
    value.claims[0].citations[0].quote = 'E2:P2'
    with pytest.raises(ValueError, match='invalid_source_span'):
        claims.expand_citations(value, sources, spans, 'I1')


@pytest.mark.asyncio
async def test_retry_preserves_other_accepted_issue_verbatim(monkeypatch):
    ctx = two_issues()
    attempts = {}

    async def generate(messages, schema, **kwargs):
        data = json.loads(messages[1]['content'])
        key = data['plan']['issues'][0]['id']
        attempts[key] = attempts.get(key, 0) + 1
        if key == 'I2' and attempts[key] == 1:
            raise ValueError('bad_output')
        return wire_claim(key, ('첫 번째' if key == 'I1' else '두 번째') + ' 요건을 충족하면 적용합니다.')

    async def judge(query, draft, context):
        return supported(draft), None

    repair = AsyncMock(return_value=ctx)
    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx, repair=repair)
    assert attempts == {'I1': 1, 'I2': 2}
    repair.assert_not_awaited()  # A malformed draft needs regeneration, not a new search.
    assert report['metrics']['issues_answered'] == 2, (report['claims'], report['issue_errors'], report['judge'])
    assert '첫 번째 요건을 충족하면 적용합니다.' in answer


@pytest.mark.asyncio
async def test_coverage_reads_late_provisions_without_cutting_requirements(monkeypatch):
    text = '제1조\n' + '요건 설명 ' * 350 + '\n① 이 끝의 예외도 확인한다.'
    from app.services.evidence import digest
    record = record_from_result(source(content=text, original_text=text, content_hash=digest(text), law_name='법인세법'))
    issue = Issue(id='I1', request_quote='질문', law='법인세법', question='예외')

    async def judge(messages, schema, **kwargs):
        data = json.loads(messages[1]['content'])[0]
        assert data['evidence'][0]['text'] == text
        assert data['evidence'][0]['excerpt_truncated'] is False
        return {'issues': [{'issue_id': 'I1', 'status': 'sufficient',
                            'relevant_evidence_ids': [record.id], 'missing_requirements': []}]}

    monkeypatch.setattr(issue_coverage, 'call_llm_structured', judge)
    assert (await issue_coverage.assess_issues([issue], {'I1': [record]}))['I1']['status'] == 'sufficient'


@pytest.mark.asyncio
async def test_financial_income_never_uses_business_calculator(monkeypatch):
    select = AsyncMock(side_effect=AssertionError('unsupported calculator'))
    monkeypatch.setattr(planner, 'select_tool', select)
    # When the deterministic calculator cannot read the inputs, the formula path follows.
    monkeypatch.setattr(planner, 'income_calculation', AsyncMock(return_value=None))
    question = '금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?'
    events = []
    result = await planner.run_tools_for_query(question, user_id='unused', on_event=events.append)
    assert result.tool == 'formula_calculation' and result.status == 'planned'
    assert events == []  # Orchestration emits progress when evidence retrieval starts.
    assert not policy.check_proposal('income_tax', {}, question, [], calculation_intent=True)[0]
    select.assert_not_called()


@pytest.mark.asyncio
async def test_financial_income_explanation_still_goes_to_retrieval():
    assert await planner.run_tools_for_query('금융소득 종합과세의 요건을 설명해줘', user_id='unused') is None


@pytest.mark.asyncio
async def test_server_records_shared_source_scope_before_checks_and_judge(monkeypatch):
    ctx = two_issues()
    ctx.plan.dates = ['2025년']
    value = wire_claim('I1')
    value['claims'][0].update(kind='source_summary', conditions=['해당 신고기한은 별도 확인이 필요합니다.'])
    monkeypatch.setattr(claims, 'call_llm_structured', AsyncMock(return_value=value))
    async def judge(query, draft, context):
        assert '확보한 원문 기준의 설명입니다.' in draft.claims[0].conditions
        assert '질문의 거래·사건 연도에 적용되는 법령 버전은 미확정입니다.' in draft.claims[0].conditions
        return supported(draft), None
    monkeypatch.setattr(claims, 'judge_claims', judge)
    draft, checks, report, judge_error, generation_error = await claims.generate_issue(
        '2025년 질문', ctx.plan.issues[0], ctx)
    assert checks[draft.claims[0].id] == []
    assert generation_error is judge_error is None
    assert '해당 신고기한은 별도 확인이 필요합니다.' in draft.claims[0].conditions
    answer = claims.render_structured_answer(draft.claims, ctx)
    assert '해당 신고기한은 별도 확인이 필요합니다.' in answer
    assert answer.count('**적용 시점:**') == 1


@pytest.mark.asyncio
async def test_one_judge_citation_error_does_not_discard_valid_claim(monkeypatch):
    from tests.test_reliability_workflow import context, draft
    ctx = context()
    value = draft(ctx)
    value.claims.append(value.claims[0].model_copy(update={'id': 'C2'}))
    response = {'claims': [
        {'claim_id': 'C1', 'support': 'supported', 'applicability': 'supported', 'evidence_ids': ['E1'], 'reason': '일치'},
        {'claim_id': 'C2', 'support': 'supported', 'applicability': 'supported', 'evidence_ids': ['FAKE'], 'reason': '잘못된 ID'}
    ], 'missing_issue_ids': []}
    monkeypatch.setattr(claims, 'call_llm_structured', AsyncMock(return_value=response))
    report, error = await claims.judge_claims('질문', value, ctx)
    released, rejected = claims.release_claims(value, claims.check_claims(value, ctx, '질문'), report, ctx.plan, mode='enforce')
    assert [c.id for c in released] == ['C1']
    assert error == 'invalid_claim_judgment' and 'C2' in rejected


@pytest.mark.asyncio
async def test_retry_is_told_which_reference_failed_and_how_to_fix_it(monkeypatch):
    ctx = two_issues()
    seen = []

    async def generate(messages, schema, **kwargs):
        data = json.loads(messages[1]['content'])
        key = data['plan']['issues'][0]['id']
        if key == 'I2':
            return wire_claim(key, '두 번째 요건을 충족하면 적용합니다.')
        seen.append(data['previous_failures'])
        if data['previous_failures'] is None:
            return wire_claim(key, '제3조에 따라 조건을 충족하면 적용합니다.')
        return wire_claim(key, '조건을 충족하면 적용합니다.')

    async def judge(query, draft, context):
        return supported(draft), None

    monkeypatch.setattr(claims, 'call_llm_structured', generate)
    monkeypatch.setattr(claims, 'judge_claims', judge)
    answer, report = await claims.generate_verified_answer('질문', ctx, repair=AsyncMock(return_value=ctx))
    assert len(seen) == 2
    failed = seen[1]['failed_claims']
    assert [row['text'] for row in failed] == ['제3조에 따라 조건을 충족하면 적용합니다.']
    assert failed[0]['cited'] == ['법인세법 제1조']
    problem = next(p for p in failed[0]['problems'] if p['code'] == 'prose_reference_mismatch')
    assert problem['category'] == 'repairable' and problem['detail'] == ['제3조'] and problem['fix']
    assert 'checks' not in seen[1]  # Bare codes keyed by IDs the model never saw are gone.
    assert report['metrics']['issues_answered'] == 2
    assert '조건을 충족하면 적용합니다.' in answer and '제3조' not in answer


def test_integrity_failures_are_not_offered_as_rewording_fixes():
    ctx = two_issues()
    value = AnswerDraft.model_validate(wire_claim('I1', '납부 세액은 500만원입니다.'))
    value.claims[0].citations[0].evidence_id = ctx.records[0].id
    value.claims[0].citations[0].quote = '조건을 충족한 경우에만 적용한다.'
    checked = claims.check_claims(value, ctx, '질문')
    _, rejected = claims.release_claims(value, checked, supported(value), ctx.plan, mode='enforce')
    problems = claims.failure_feedback(value, rejected, supported(value), ctx, '질문')[0]['problems']
    assert {'code': 'generated_tax_amount_without_calculator', 'category': 'integrity'} in problems


def test_every_withholding_code_has_one_retry_category():
    import inspect, re
    source_text = inspect.getsource(claims)
    emitted = set(re.findall(r'errors\.append\("([a-z_]+)"\)', source_text))
    emitted |= set(re.findall(r'(?:reasons\.append|rejected\[claim\.id\] =)\(?\[?"([a-z_]+)"', source_text))
    emitted.add('prose_reference_mismatch')
    groups = (claims.INTEGRITY_ERRORS, claims.REPAIRABLE_ERRORS, claims.EVIDENCE_ERRORS)
    assert emitted and all(sum(code in group for group in groups) == 1 for code in emitted), emitted
    assert set(claims.FIX_HINTS) <= set().union(*groups)

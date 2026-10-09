"""Arithmetic/provenance/release tests use synthetic rules, not tax accuracy claims."""
from datetime import datetime
import json
from decimal import Decimal
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo
from uuid import uuid4

import pytest

from app.schemas.formula import FormulaPlan
from app.services.calculator import formula_engine as engine, formula_workflow as workflow
from app.services.evidence import context_from_records
from app.services import chat_service as chat
from tests.test_reliability_workflow import source
from app.services.evidence import record_from_result


def context():
    text = '제1조\n시험 규정: 금액에 100분의 10을 곱한다. 구간은 1,000원 이하 10퍼센트, 2,000원 이하 20퍼센트이다.'
    from app.services.evidence import digest
    return context_from_records([record_from_result(source(content=text, original_text=text, content_hash=digest(text)))])


def plan():
    return FormulaPlan.model_validate({
        'title': '시험 참고 계산', 'reference_date': datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),
        'scope': '합성 규정의 계산 검증', 'assumptions': [], 'follow_up': [],
        'rules': [{'id': 'rule', 'evidence_id': 'E1', 'span_ids': ['E1:P2'], 'description': '시험 비율'}],
        'values': [
            {'id': 'amount', 'label': '금액', 'value': '1000', 'unit': 'KRW', 'origin': 'user', 'quote': '1,000원', 'rule_id': ''},
            {'id': 'rate', 'label': '비율', 'value': '0.1', 'unit': 'ratio', 'origin': 'law', 'quote': '', 'rule_id': 'rule'},
        ], 'tables': [],
        'steps': [{'id': 'tax', 'label': '계산값', 'op': 'multiply', 'args': ['amount', 'rate'],
                   'table_id': '', 'rule_ids': ['rule'], 'rounding': 'none'}],
        'outputs': [{'label': '참고 산출액', 'step_id': 'tax', 'role': 'total'}],
    })


def test_decimal_execution_is_exact_and_original_inputs_are_preserved():
    value = plan()
    before = value.model_dump()
    result = engine.execute(value)
    assert Decimal(result['outputs'][0]['value']) == 100
    assert value.model_dump() == before
    value.values[0].value = '0.3'
    assert Decimal(engine.execute(value)['outputs'][0]['value']) == Decimal('0.03')


@pytest.mark.parametrize('literal', ['nan', 'Infinity', '1e30', '__import__("os")', '0.1+1', '9'*19])
def test_numeric_parser_rejects_code_nonfinite_and_unbounded_values(literal):
    with pytest.raises(engine.FormulaError): engine.number(literal)


@pytest.mark.parametrize('mutation,expected', [
    (lambda p: setattr(p.steps[0], 'args', ['future', 'rate']), 'unknown_or_forward'),
    (lambda p: setattr(p.steps[0], 'id', 'amount'), 'duplicate_step'),
    (lambda p: setattr(p.steps[0], 'args', ['amount', 'amount']), 'money_squared'),
    (lambda p: setattr(p.steps[0], 'op', 'add'), 'incompatible_units'),
])
def test_invalid_arithmetic_graph_is_rejected(mutation, expected):
    value = plan(); mutation(value)
    with pytest.raises(engine.FormulaError, match=expected): engine.execute(value)


def test_division_by_zero_is_not_a_zero_tax_result():
    value = plan(); value.values[1].value = '0'; value.steps[0].op = 'divide'
    with pytest.raises(engine.FormulaError, match='invalid_division'): engine.execute(value)


def test_progressive_tax_uses_marginal_bands_and_rejects_incomplete_or_disordered_table():
    value = plan().model_dump()
    value['values'][0]['value'] = '1500'
    value['tables'] = [{'id': 'bands', 'rule_id': 'rule', 'bands': [
        {'upper': '1000', 'rate': '0.1'}, {'upper': '2000', 'rate': '0.2'}]}]
    value['steps'][0].update(op='progressive', args=['amount'], table_id='bands')
    model = FormulaPlan.model_validate(value)
    assert Decimal(engine.execute(model)['outputs'][0]['value']) == 200
    model.values[0].value = '2500'
    with pytest.raises(engine.FormulaError, match='incomplete_rate_table'): engine.execute(model)
    model.tables[0].bands[1].upper = '500'
    with pytest.raises(engine.FormulaError, match='unordered_bands'): engine.execute(model)


def test_total_and_balance_must_reconcile():
    value = plan()
    value.outputs.append(value.outputs[0].model_copy(update={'role': 'prepaid'}))
    value.outputs.append(value.outputs[0].model_copy(update={'role': 'balance'}))
    with pytest.raises(engine.FormulaError, match='balance_mismatch'): engine.execute(value)


def test_numeric_grounding_handles_compound_korean_money_and_percentages():
    values = workflow.numeric_samples('1억 5천만원, 150만원, 100분의 14, 1.4퍼센트')
    assert {Decimal(150000000), Decimal(1500000), Decimal('0.14'), Decimal('0.014')} <= values
    assert Decimal(100000000) not in values
    assert workflow.scaled_number('1천400만원') == Decimal(14000000)
    assert workflow.scaled_number('8천800만원') == Decimal(88000000)
    assert workflow.scaled_number('0만원') == 0
    assert workflow.numeric_samples('-1,000원') == {Decimal(-1000)}
    assert {Decimal(14000000), Decimal('0.006')} <= workflow.numeric_samples('1천400만원 이하 1천분의 6')
    value = plan(); value.values[0].value = '100000000'; value.values[0].quote = '1억'
    with pytest.raises(engine.FormulaError, match='unconfirmed_user_value'):
        workflow.ground_plan(value, context(), '1억 5천만원', [], value.reference_date)


def test_source_provenance_and_numeric_binding_are_required():
    value = plan()
    rules, used = workflow.ground_plan(value, context(), '1,000원 계산해줘', [], value.reference_date)
    assert '100분의 10' in rules['rule'] and len(used) == 1
    value.values[1].value = '0.3'
    with pytest.raises(engine.FormulaError, match='ungrounded_law_value'):
        workflow.ground_plan(value, context(), '1,000원', [], value.reference_date)
    value = plan(); value.rules[0].span_ids = ['E99:P2']
    with pytest.raises(engine.FormulaError, match='invalid_source_span'):
        workflow.ground_plan(value, context(), '1,000원', [], value.reference_date)


def test_uploaded_material_cannot_become_official_calculation_rules():
    ctx = context(); record = ctx.records[0].model_copy(update={'origin': 'user_document'})
    value = plan()
    with pytest.raises(engine.FormulaError, match='unverified_or_undated_source'):
        workflow.ground_plan(value, context_from_records([record]), '1,000원', [], value.reference_date)


def test_legal_rates_cannot_be_smuggled_in_as_assumptions_or_arithmetic_constants():
    value = plan(); value.values[1].origin = 'assumption'; value.assumptions = ['비율 가정']
    with pytest.raises(engine.FormulaError, match='unconfirmed_rate'):
        workflow.ground_plan(value, context(), '1,000원', [], value.reference_date)
    value.values[1].origin = 'constant'
    with pytest.raises(engine.FormulaError, match='non_arithmetic_constant'):
        workflow.ground_plan(value, context(), '1,000원', [], value.reference_date)


def review(supported):
    return {'arithmetic_meaning_supported': supported, 'user_facts_preserved': True,
            'rules_complete': supported, 'scope_and_assumptions_clear': True,
            'issues': [] if supported else ['산식의 적용 근거 부족']}


@pytest.mark.asyncio
@pytest.mark.parametrize('supported', [True, False])
async def test_only_reviewed_formulas_are_released_and_failure_keeps_evidence(monkeypatch, supported):
    value = plan()
    monkeypatch.setattr(workflow, 'collect_sources', AsyncMock(return_value=context()))
    async def llm(messages, schema, **kwargs):
        return review(supported) if kwargs['purpose'] == 'answer_judge' else value.model_dump()
    monkeypatch.setattr(workflow, 'call_llm_structured', llm)
    events = []
    ctx, calc = await workflow.calculate_reference('1,000원 계산해줘', [], 'unused', AsyncMock(), events.append)
    assert ctx.records
    if supported:
        assert calc.verification['checks']['calculation'] == 'checked'
        assert calc.verification['status'] == 'limited'
        assert '100.0원' in calc.context or '100원' in calc.context
        assert chat._calc_meta(calc) is None
        assert events[-1]['status'] == 'ok'
    else:
        assert calc is None and ctx.plan is not None
        assert events[-1]['status'] == 'not_found'
        assert chat._failed_tool_answer(events) is None
        assert all('100원' not in event.get('context', '') for event in events)


@pytest.mark.asyncio
async def test_financial_chat_routes_to_generic_workflow_instead_of_early_abstention(monkeypatch):
    from app.services.calculator.engine import CalcRun
    result = CalcRun('검증한 참고 계산', 'formula_calculation', {}, verification={'status': 'limited'})
    fallback = AsyncMock(return_value=(context(), result))
    monkeypatch.setattr(workflow, 'calculate_reference', fallback)
    from app.services.tools import planner
    monkeypatch.setattr(planner, 'financial_calculation', AsyncMock(return_value=None))  # calculator unavailable
    query = '금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?'
    ctx, _, _, calc = await chat._fetch_rag_and_web_context(query, uuid4(), str(uuid4()), history_override=[])
    fallback.assert_awaited_once()
    assert calc is result
    answer, report = await chat._answer_evidence_context(query, ctx, calc, 'unused')
    assert answer == '검증한 참고 계산' and report['status'] == 'limited'


@pytest.mark.asyncio
async def test_repair_receives_rejected_plan_and_specific_feedback(monkeypatch):
    value = plan()
    monkeypatch.setattr(workflow, 'collect_sources', AsyncMock(return_value=context()))
    plans, reviews = [], []
    async def llm(messages, schema, **kwargs):
        if kwargs['purpose'] == 'answer_judge':
            reviews.append(True)
            return review(len(reviews) == 2)
        plans.append(json.loads(messages[-1]['content']))
        return value.model_dump()
    monkeypatch.setattr(workflow, 'call_llm_structured', llm)
    _, calc = await workflow.calculate_reference('1,000원 계산해줘', [], 'unused', AsyncMock())
    assert calc is not None
    assert plans[0]['previous_plan'] is None
    assert plans[1]['previous_plan'] == value.model_dump()
    assert plans[1]['previous_errors'] == ['산식의 적용 근거 부족']


@pytest.mark.asyncio
async def test_historical_request_cannot_silently_use_current_formula(monkeypatch):
    monkeypatch.setattr(workflow, 'collect_sources', AsyncMock(return_value=context()))
    llm = AsyncMock()
    monkeypatch.setattr(workflow, 'call_llm_structured', llm)
    ctx, calc = await workflow.calculate_reference('2020년 1,000원 계산해줘', [], 'unused', AsyncMock())
    assert calc is None and ctx.records
    assert ctx.coverage['F1']['formula_diagnostics']['reason'] == 'historical_formula_version_required'
    llm.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('supported', [True, False])
async def test_composite_formula_preserves_full_user_context_and_failure_explanation(monkeypatch, supported):
    from app.services import reliable_workflow as reliable
    from app.schemas.reliability import Issue, QuestionPlan
    from app.services.tools.executor import ToolRun
    from app.services.calculator.engine import CalcRun
    query = '금융소득 1억원이고 다른 소득은 없습니다. 계산해줘. 신고 절차도 설명해줘.'
    question_plan = QuestionPlan(issues=[Issue(id='F1', kind='calculation', law='소득세법',
                                              request_quote='계산해줘.', question='세액 계산')])
    monkeypatch.setattr(reliable, 'plan_question', AsyncMock(return_value=question_plan))
    monkeypatch.setattr(reliable, 'retrieve_issues', AsyncMock(return_value=context_from_records([], plan=question_plan)))
    monkeypatch.setattr(reliable, 'run_tools_for_query', AsyncMock(return_value=ToolRun('formula_calculation', 'planned', '')))
    calc = CalcRun('검증된 예시 계산', 'formula_calculation', {}, verification={'status': 'limited'}) if supported else None
    calculate = AsyncMock(return_value=(context(), calc))
    monkeypatch.setattr(workflow, 'calculate_reference', calculate)
    prepared = await reliable.prepare_context(query, [], 'unused', [], AsyncMock())
    assert calculate.await_args.args[1][-1]['content'] == query
    assert prepared.records
    if supported:
        assert prepared.coverage['F1']['calculation']['verification']['status'] == 'limited'
    else:
        assert prepared.plan.issues[0].kind == 'analysis'

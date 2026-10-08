"""Formula plans: the server completes a missing balance and explains other rejections."""
import inspect
import json
import re
from unittest.mock import AsyncMock

import pytest

from app.schemas.formula import FormulaPlan
from app.services.calculator import formula_engine as engine, formula_workflow as workflow
from app.services.calculator.formula_feedback import HINTS, formula_feedback
from tests.test_formula_calculation import context, plan, review


def with_prepaid(balance=False, rate='0.05'):
    """Total 100원 at 10%, prepaid at `rate`; optionally the planner's own balance step."""
    data = plan().model_dump()
    data['values'].append({'id': 'withheld_rate', 'label': '원천징수율', 'value': rate, 'unit': 'ratio',
                           'origin': 'law', 'quote': '', 'rule_id': 'rule'})
    data['steps'].append({'id': 'paid', 'label': '원천징수 예시액', 'op': 'multiply',
                          'args': ['amount', 'withheld_rate'], 'table_id': '', 'rule_ids': ['rule'], 'rounding': 'none'})
    data['outputs'].append({'label': '원천징수 예시액', 'step_id': 'paid', 'role': 'prepaid'})
    if balance:
        data['steps'].append({'id': 'left', 'label': '차감액', 'op': 'subtract', 'args': ['tax', 'paid'],
                              'table_id': '', 'rule_ids': ['rule'], 'rounding': 'none'})
        data['outputs'].append({'label': '차감액', 'step_id': 'left', 'role': 'balance'})
    return FormulaPlan.model_validate(data)


def test_prepaid_without_balance_gets_the_one_correct_subtraction():
    completed = engine.complete_balance(with_prepaid())
    step = next(s for s in completed.steps if s.id == engine.BALANCE_STEP)
    assert (step.op, step.args, step.rule_ids, step.rounding) == ('subtract', ['tax', 'paid'], ['rule'], 'none')
    assert '서버 산출' in step.label
    outputs = {o['role']: o['value'] for o in engine.execute(completed)['outputs']}
    assert (outputs['total'], outputs['prepaid'], outputs['balance']) == ('100.0', '50.00', '50.00')


def test_plans_that_need_no_completion_or_have_no_single_meaning_are_untouched():
    own_balance = with_prepaid(balance=True)
    assert engine.complete_balance(own_balance) == own_balance
    assert engine.complete_balance(plan()) == plan()               # no prepaid at all
    balance_only = plan()
    balance_only.outputs.append(balance_only.outputs[0].model_copy(update={'role': 'balance'}))
    assert engine.complete_balance(balance_only) == balance_only
    with pytest.raises(engine.FormulaError, match='missing_prepaid_or_balance'):
        engine.execute(balance_only)


def test_every_rule_a_plan_can_break_is_explained():
    raised = set()
    for module in (engine, workflow):
        raised |= set(re.findall(r"FormulaError\(['\"]([a-z_]+)", inspect.getsource(module)))
    # Raised outside the retry loop: they end the calculation and are never fed back.
    not_retried = {'formula_review_incomplete', 'historical_formula_version_required', 'no_official_formula_evidence'}
    assert raised - not_retried <= set(HINTS), (raised - not_retried) - set(HINTS)


def test_feedback_keeps_the_code_and_adds_meaning_and_fix():
    message = formula_feedback(engine.FormulaError('missing_prepaid_or_balance'))
    assert message.startswith('missing_prepaid_or_balance: ') and 'subtract step' in message
    detailed = formula_feedback(engine.FormulaError('ungrounded_law_value:rate'))
    assert detailed.startswith('ungrounded_law_value:rate: ') and '원문' in detailed
    assert formula_feedback(ValueError('1 validation error for FormulaPlan')) == '1 validation error for FormulaPlan'
    assert formula_feedback(engine.FormulaError('unlisted_code')) == 'unlisted_code'


def scripted(monkeypatch, *plans):
    monkeypatch.setattr(workflow, 'collect_sources', AsyncMock(return_value=context()))
    sent = []

    async def llm(messages, schema, **kwargs):
        if kwargs['purpose'] == 'answer_judge':
            return review(True)
        sent.append(json.loads(messages[-1]['content']))
        return plans[min(len(sent), len(plans)) - 1].model_dump()

    monkeypatch.setattr(workflow, 'call_llm_structured', llm)
    return sent


@pytest.mark.asyncio
async def test_missing_balance_no_longer_costs_a_retry(monkeypatch):
    # The synthetic source states 10 and 20 percent; grounding rejects any other rate.
    sent = scripted(monkeypatch, with_prepaid(rate='0.2'))
    _, calc = await workflow.calculate_reference('1,000원 계산해줘', [], 'unused', AsyncMock())
    assert calc is not None and len(sent) == 1
    assert '| 차감 납부(환급) 세액 (계산 범위 내 환급 방향) | -100원 |' in calc.context


@pytest.mark.asyncio
async def test_a_rule_the_server_cannot_complete_is_explained_to_the_second_attempt(monkeypatch):
    balance_only = plan()
    balance_only.outputs.append(balance_only.outputs[0].model_copy(update={'role': 'balance'}))
    sent = scripted(monkeypatch, balance_only, plan())
    _, calc = await workflow.calculate_reference('1,000원 계산해줘', [], 'unused', AsyncMock())
    assert calc is not None and len(sent) == 2
    assert sent[1]['previous_errors'] == [formula_feedback(engine.FormulaError('missing_prepaid_or_balance'))]
    assert 'prepaid와 balance는 반드시 함께 쓰거나 둘 다 빼세요' in workflow.PLAN_PROMPT

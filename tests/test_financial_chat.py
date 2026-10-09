"""A financial-income tax question in chat: deterministic calculator first, formula path as fallback."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service as chat
from app.services.calculator import financial_income_tax as fit, repository
from app.services.calculator.errors import CalculationError
from app.services.calculator.financial_inputs import parse_money, stated_financial_inputs
from app.services.tools import planner
from tests.test_financial_income_api import current_parameters

QUESTION = '금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?'


@pytest.fixture
def stored_figures(monkeypatch):
    async def deduction(tax_type, name, as_of=None):
        assert (tax_type, name) == ('소득세', '기본공제')
        return {'amount': 1_500_000}

    async def load(as_of=None):
        return current_parameters()
    monkeypatch.setattr(repository, 'get_deduction', deduction)
    monkeypatch.setattr(fit, 'load_parameters', load)


@pytest.mark.parametrize('text, value', [('1억 5천만원', 150_000_000), ('1억 5천', 150_000_000),
                                         ('2,000만원', 20_000_000), ('300만원', 3_000_000)])
def test_korean_amounts(text, value):
    assert parse_money(text) == value


def test_one_stated_amount_is_completed_by_visible_assumptions():
    stated = stated_financial_inputs(QUESTION, basic_deduction=1_500_000)
    assert stated.params == {'interest_income': 100_000_000, 'non_business_interest': 0, 'dividend_gross_up': 0,
                             'dividend_other': 0, 'other_income': 0, 'income_deductions': 1_500_000, 'withheld': True}
    text = ' '.join(stated.assumptions)
    assert '국내 예금 이자' in text and '다른 종합소득은 없다' in text and '기본공제' in text and '원천징수' in text


def test_stated_values_override_the_assumptions():
    stated = stated_financial_inputs('이자소득 6천만원, 사업소득금액 3천만원, 소득공제 510만원이면 세금 계산해줘',
                                     basic_deduction=1_500_000)
    assert stated.params['other_income'] == 30_000_000 and stated.params['income_deductions'] == 5_100_000
    assert not any('기본공제' in a or '다른 종합소득' in a for a in stated.assumptions)
    unwithheld = stated_financial_inputs('배당 3천만원 받았는데 원천징수되지 않았어요. 세금 계산해줘', basic_deduction=1)
    assert unwithheld.params['withheld'] is False and unwithheld.params['dividend_gross_up'] == 30_000_000


@pytest.mark.parametrize('query', [
    '이자 1억 5000이면 세금 얼마야?',                       # the rest of the amount has no unit
    '금융소득 1억, 이자 5천만원 세금 계산해줘',               # a total and a part together
    '해외 배당 5천만원이면 세금 얼마?',                       # foreign income: not modelled
    '출자공동사업자 배당 3천만원 세금 계산해줘',
    '비영업대금 이자 1천만원과 예금이자 3천만원 세금 계산해줘',  # one label, two amounts
    '종합소득세 계산해줘',                                     # no financial amount
])
def test_unreadable_or_unsupported_questions_are_left_to_the_formula_path(query):
    assert stated_financial_inputs(query, basic_deduction=1_500_000) is None


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator_and_its_assumptions(monkeypatch, stored_figures):
    select = AsyncMock(side_effect=AssertionError('tool selection is not needed'))
    monkeypatch.setattr(planner, 'select_tool', select)
    events = []
    result = await planner.run_tools_for_query(QUESTION, user_id=str(uuid4()), on_event=events.append)
    assert (result.tool, result.status) == ('financial_income_tax', 'ok')
    context = result.calculation.context
    assert context.startswith('계산에 쓴 가정:')
    assert '- ① 종합과세 방식 산출세액: 15,880,000원' in context
    assert '- 차감 납부할 세액: 1,880,000원' in context
    assert [e['status'] for e in events] == ['running', 'ok']
    select.assert_not_called()


@pytest.mark.asyncio
async def test_chat_answer_is_the_calculator_output(monkeypatch, stored_figures):
    formula = AsyncMock(side_effect=AssertionError('formula path is not needed'))
    from app.services.calculator import formula_workflow
    monkeypatch.setattr(formula_workflow, 'calculate_reference', formula)
    ctx, _, _, calc = await chat._fetch_rag_and_web_context(QUESTION, uuid4(), str(uuid4()), history_override=[])
    answer, report = await chat._answer_evidence_context(QUESTION, ctx, calc, 'unused')
    assert calc.tool == 'financial_income_tax' and answer == calc.context
    assert report['checks']['calculation'] == 'checked'


@pytest.mark.asyncio
async def test_calculator_failure_falls_back_to_the_formula_path(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise CalculationError('missing_tax_data')
    monkeypatch.setattr(repository, 'get_deduction', unavailable)
    result = await planner.run_tools_for_query(QUESTION, user_id=str(uuid4()))
    assert (result.tool, result.status) == ('formula_calculation', 'planned')

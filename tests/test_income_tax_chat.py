"""A comprehensive income tax question in chat: the calculator reads the stated incomes, asks for the
facts that decide the deduction and credit, and leaves unmodelled cases to another path."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service as chat
from app.services.calculator import income_tax as it, repository
from app.services.calculator.errors import CalculationError
from app.services.calculator.financial_inputs import parse_money
from app.services.calculator.income_tax_inputs import MissingInputs, StatedInputs, stated_income_tax_inputs
from app.services.tools import planner
from tests.test_income_tax import params

FINANCIAL = '금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?'
WAGE = '연봉 5천만원이면 종합소득세 얼마야?'


def read(query, history=None):
    return stated_income_tax_inputs(query, history, basic_deduction=1_500_000)


@pytest.fixture
def stored_figures(monkeypatch):
    async def deduction(tax_type, name, as_of=None):
        assert (tax_type, name) == ('소득세', '기본공제')
        return {'amount': 1_500_000}

    async def load(as_of=None):
        return params()
    monkeypatch.setattr(repository, 'get_deduction', deduction)
    monkeypatch.setattr(it, 'load_parameters', load)


@pytest.mark.parametrize('text, value', [('1억 5천만원', 150_000_000), ('1억 5천', 150_000_000),
                                         ('2,000만원', 20_000_000), ('300만원', 3_000_000)])
def test_korean_amounts(text, value):
    assert parse_money(text) == value


def test_one_financial_amount_is_completed_by_visible_assumptions():
    stated = read(FINANCIAL)
    assert stated.params['interest_income'] == 100_000_000 and stated.params['withheld'] is True
    assert (stated.params['personal_deduction_count'], stated.params['other_deductions']) == (1, 0)
    text = ' '.join(stated.assumptions)
    assert '국내 예금 이자' in text and '근로소득·사업소득·기타·연금소득은 없다' in text and '기본공제' in text


def test_a_salary_is_read_as_total_salary():
    stated = read(WAGE)
    assert stated.params['wage_income'] == 50_000_000 and stated.params['income'] == 0
    assert any('총급여액' in a for a in stated.assumptions)


def test_stated_values_override_the_assumptions():
    stated = read('이자소득 6천만원, 사업소득금액 3천만원, 소득공제 510만원이면 세금 계산해줘')
    assert (stated.params['income'], stated.params['expense'], stated.params['interest_income']) == (
        30_000_000, 0, 60_000_000)
    assert (stated.params['personal_deduction_count'], stated.params['other_deductions']) == (0, 5_100_000)
    unwithheld = read('배당 3천만원 받았는데 원천징수되지 않았어요. 세금 계산해줘')
    assert unwithheld.params['withheld'] is False and unwithheld.params['dividend_gross_up'] == 30_000_000
    family = read('수입 1억, 경비 6천만원, 부양가족 2명이면 종합소득세 계산해줘')
    assert family.params['personal_deduction_count'] == 3 and family.params['expense'] == 60_000_000


@pytest.mark.parametrize('query, label', [
    ('소득 5천만원이면 종합소득세 얼마야?', '소득의 종류'),
    ('사업 수입 1억이면 종합소득세 얼마야?', '필요경비'),
    ('근로소득금액 3천만원이면 세금 얼마?', '총급여액'),
    ('기타소득 2천만원 있으면 세금 얼마?', '기타소득금액'),
    ('수입 1억 경비 7천이면 소득세 얼마?', "'7천'의 단위"),
])
def test_facts_that_decide_the_tax_are_asked_not_assumed(query, label):
    stated = read(query)
    assert isinstance(stated, MissingInputs)
    assert any(label in item for item in stated.labels), stated.labels


@pytest.mark.parametrize('query', [
    '이자 1억 5000이면 세금 얼마야?',                       # the rest of the amount has no unit
    '금융소득 1억, 이자 5천만원 세금 계산해줘',               # a total and a part together
    '해외 배당 5천만원이면 세금 얼마?',                       # foreign income: not modelled
    '출자공동사업자 배당 3천만원 세금 계산해줘',
    '비영업대금 이자 1천만원과 예금이자 3천만원 세금 계산해줘',  # one label, two amounts
    '월급 300만원이면 소득세 얼마야?',                        # a monthly amount is not annual income
    '연봉 5천만원인데 의료비가 500만원이면 세금 얼마?',        # itemized credits are not modelled
    '종합소득세 계산해줘',                                     # no amount at all
])
def test_unreadable_or_unsupported_questions_are_left_to_another_path(query):
    assert read(query) is None


def test_a_follow_up_replaces_the_financial_amount():
    history = [{'role': 'user', 'content': '금융소득 1억이면 세금 얼마야?'}]
    stated = read('이자 1억 5천이면?', history)
    assert stated.params['interest_income'] == 150_000_000


@pytest.mark.asyncio
async def test_chat_answers_a_salary_question_with_the_calculator(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    events = []
    result = await planner.run_tools_for_query(WAGE, user_id=str(uuid4()), on_event=events.append)
    assert (result.tool, result.status) == ('income_tax', 'ok')
    context = result.calculation.context
    assert context.startswith('계산에 쓴 가정:')
    # 5,000만 - 근로소득공제 1,225만 = 3,775만 - 150만 = 3,625만 x 15% - 126만 = 4,177,500
    assert '- 과세표준: 36,250,000원' in context and '산출세액(기본세율 15%): 4,177,500원' in context
    # 근로소득세액공제 한도 74만 - 1,700만 x 0.8% = 604,000 -> 66만; 표준세액공제 13만
    assert '근로소득세액공제(총급여액 기준 한도 660,000원): 660,000원' in context
    assert '- 결정세액: 3,387,500원' in context
    assert [e['status'] for e in events] == ['running', 'ok']


@pytest.mark.asyncio
async def test_chat_answers_a_financial_question_with_the_same_calculator(monkeypatch, stored_figures):
    select = AsyncMock(side_effect=AssertionError('tool selection is not needed'))
    monkeypatch.setattr(planner, 'select_tool', select)
    result = await planner.run_tools_for_query(FINANCIAL, user_id=str(uuid4()))
    assert (result.tool, result.status) == ('income_tax', 'ok')
    context = result.calculation.context
    assert '- ① 종합과세 방식 산출세액: 15,880,000원' in context
    assert '- 표준세액공제: 70,000원' in context and '- 차감 납부할 세액: 1,810,000원' in context
    select.assert_not_called()


@pytest.mark.asyncio
async def test_chat_answer_is_the_calculator_output(monkeypatch, stored_figures):
    formula = AsyncMock(side_effect=AssertionError('formula path is not needed'))
    from app.services.calculator import formula_workflow
    monkeypatch.setattr(formula_workflow, 'calculate_reference', formula)
    ctx, _, _, calc = await chat._fetch_rag_and_web_context(FINANCIAL, uuid4(), str(uuid4()), history_override=[])
    answer, report = await chat._answer_evidence_context(FINANCIAL, ctx, calc, 'unused')
    assert calc.tool == 'income_tax' and answer == calc.context
    assert report['checks']['calculation'] == 'checked'


@pytest.mark.asyncio
async def test_chat_asks_for_the_kind_of_income_without_calling_the_model(monkeypatch):
    async def deduction(tax_type, name, as_of=None):
        return {'amount': 1_500_000}
    monkeypatch.setattr(repository, 'get_deduction', deduction)
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('소득 5천만원이면 종합소득세 얼마야?', user_id=str(uuid4()))
    assert (result.tool, result.status, result.error_code) == ('income_tax', 'needs_input', 'calculation_inputs_required')
    assert '소득의 종류' in result.context


@pytest.mark.asyncio
async def test_calculator_failure_falls_back_to_the_formula_path_for_financial_income(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise CalculationError('missing_tax_data')
    monkeypatch.setattr(repository, 'get_deduction', unavailable)
    result = await planner.run_tools_for_query(FINANCIAL, user_id=str(uuid4()))
    assert (result.tool, result.status) == ('formula_calculation', 'planned')


@pytest.mark.asyncio
async def test_a_capital_gains_question_is_not_read_as_income_tax(monkeypatch):
    income = AsyncMock(side_effect=AssertionError('not an income tax question'))
    monkeypatch.setattr(planner, 'income_calculation', income)
    monkeypatch.setattr(planner, 'capital_gains_calculation', AsyncMock(return_value=None))
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(return_value=None))
    await planner.run_tools_for_query('10억에 산 아파트를 15억에 팔면 양도소득세 얼마야?', user_id=str(uuid4()))

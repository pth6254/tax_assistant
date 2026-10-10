"""An inheritance tax question in chat: the calculator reads the estate and the heirs, asks for the
facts that decide the deductions, and leaves unmodelled inheritances to the ordinary path."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import inheritance as ih
from app.services.calculator.inheritance_inputs import MissingInputs, StatedInputs, stated_inheritance_inputs
from app.services.tools import planner
from tests.test_inheritance import params

QUESTION = '아버지가 돌아가셨는데 상속재산이 20억이야. 어머니와 자녀 2명이 상속받으면 상속세 얼마야?'


@pytest.fixture
def stored_figures(monkeypatch):
    async def load(as_of=None):
        return params()
    monkeypatch.setattr(ih, 'load_parameters', load)


@pytest.mark.parametrize('query, expected', [
    (QUESTION, {'estate_value': 2_000_000_000, 'has_spouse': True, 'children_count': 2, 'spouse_inheritance': 0}),
    ('어머니가 돌아가셨어. 아버지는 먼저 돌아가셨고 자녀 2명이 상속재산 10억을 상속받으면 상속세는?',
     {'has_spouse': False, 'children_count': 2}),
    ('상속재산 30억, 배우자 몫 10억, 자녀 3명, 예금 5억, 채무 2억이면 상속세 계산해줘',
     {'spouse_inheritance': 1_000_000_000, 'financial_assets': 500_000_000, 'debts': 200_000_000, 'children_count': 3}),
    ('상속재산 20억, 배우자 있고 자녀 1명, 사전증여 3억 있어. 상속세 얼마?', {'prior_gifts': 300_000_000}),
    ('상속재산 10억, 배우자 있고 1남 1녀야. 상속세 얼마?', {'children_count': 2}),
])
def test_stated_inheritances_are_read(query, expected):
    stated = stated_inheritance_inputs(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params[k] for k in expected} == expected


def test_unstated_facts_are_assumed_without_understating_the_tax():
    text = ' '.join(stated_inheritance_inputs(QUESTION).assumptions)
    assert '최소 5억원' in text and '금융재산' in text and '증여한 재산은 없다고' in text


@pytest.mark.parametrize('query, label', [
    ('유산이 10억이면 상속세 얼마야?', '배우자'),
    ('유산이 10억이면 상속세 얼마야? 배우자 있어', '자녀 수'),
    ('상속재산 20억, 배우자 있고 자녀 1명, 5년 전에 자녀에게 증여한 게 있어. 상속세 얼마?', '증여한 재산의 금액'),
    ('상속재산 20억, 배우자와 미성년 자녀 1명이면 상속세 얼마?', '미성년'),
])
def test_facts_that_decide_the_tax_are_asked_not_assumed(query, label):
    stated = stated_inheritance_inputs(query)
    assert isinstance(stated, MissingInputs)
    assert any(label in item for item in stated.labels), stated.labels


@pytest.mark.parametrize('query', [
    '할아버지가 돌아가셔서 손자가 상속받으면 상속세 얼마?',
    '상속재산 20억인데 자녀들이 상속포기하면 상속세 얼마?',
    '가업 상속으로 30억이면 상속세 얼마?',
    '상속세 얼마야?',
])
def test_unmodelled_or_unreadable_inheritances_take_the_ordinary_path(query):
    assert stated_inheritance_inputs(query) is None


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator_and_its_assumptions(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    events = []
    result = await planner.run_tools_for_query(QUESTION, user_id=str(uuid4()), on_event=events.append)
    assert (result.tool, result.status) == ('inheritance', 'ok')
    context = result.calculation.context
    assert context.startswith('계산에 쓴 가정:')
    # 20억 - 장례 500만 - 일괄 5억 - 배우자 5억 = 9.95억 x 30% - 6천만 = 2.385억, 신고세액공제 715.5만
    assert '- 상속세 과세표준: 995,000,000원' in context and '- 납부할 세액: 231,345,000원' in context
    assert [e['status'] for e in events] == ['running', 'ok']


@pytest.mark.asyncio
async def test_chat_asks_for_the_heirs_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('유산이 10억이면 상속세 얼마야?', user_id=str(uuid4()))
    assert (result.tool, result.status, result.error_code) == ('inheritance', 'needs_input', 'calculation_inputs_required')
    assert '자녀 수' in result.context

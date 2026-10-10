"""A gift tax question in chat: the calculator reads the amount and the relation, asks for the facts
that decide the deduction, and leaves unmodelled gifts to the ordinary path."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import gift_tax as gt
from app.services.calculator.gift_inputs import MissingInputs, StatedInputs, stated_gift_inputs
from app.services.tools import planner
from tests.test_gift_tax import params

QUESTION = '성인인 아들에게 3억 증여하면 증여세 얼마야?'


@pytest.fixture
def stored_figures(monkeypatch):
    async def load(as_of=None):
        return params()
    monkeypatch.setattr(gt, 'load_parameters', load)


@pytest.mark.parametrize('query, expected', [
    (QUESTION, {'gift_amount': 300_000_000, 'relation': '직계존비속', 'is_minor': False}),
    ('남편에게 8억 증여받으면 증여세 얼마?', {'relation': '배우자', 'gift_amount': 800_000_000}),
    ('할아버지가 대학생 손자에게 1억 주면 증여세 얼마?', {'relation': '직계존비속', 'generation_skipping': True}),
    ('할아버지가 손자에게 1억 주면 증여세 얼마? 손자 아버지는 돌아가셨어. 성인이야', {'generation_skipping': False}),
    ('결혼 앞두고 어머니에게 1억 5천만원 받으면 증여세 얼마야? 30살이야', {'marriage_birth': True}),
    ('삼촌한테 5천만원 증여받으면 세금 얼마?', {'relation': '기타친족'}),
    ('시아버지가 1억 주면 증여세 얼마야?', {'relation': '기타친족'}),
    ('친구가 2천만원 주면 증여세 얼마?', {'relation': '기타'}),
    ('아들이 나한테 1억 주면 증여세 얼마?', {'relation': '직계존비속', 'is_minor': False}),
    ('어머니에게 1억 증여받으면 증여세 얼마야? 사전증여 5천만원 있어. 성인이야', {'prior_gifts_10y': 50_000_000}),
    ('시가 5억 아파트(전세보증금 2억)를 성인 아들에게 증여하면 증여세 얼마?', {'gift_amount': 500_000_000, 'debts': 200_000_000}),
    ('미성년 딸에게 5천만원 증여하면 증여세 얼마?', {'is_minor': True}),
])
def test_stated_gifts_are_read(query, expected):
    stated = stated_gift_inputs(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params[k] for k in expected} == expected


@pytest.mark.parametrize('query, label', [
    ('3억 증여받으면 증여세 얼마?', '관계'),
    ('아버지한테 3억 증여받으면 증여세 얼마야?', '미성년자'),
    ('결혼하는데 엄마한테 2억 받으면 증여세? 성인이야', '2년 이내'),
    ('예전에 아버지에게 받은 적 있는데 이번에 성인 아들인 내가 3억 증여받으면 증여세 얼마?', '이전 증여액'),
    ('아버지한테 3천 증여받으면 증여세 얼마야? 성인이야', "'3천'의 단위"),
])
def test_facts_that_decide_the_tax_are_asked_not_assumed(query, label):
    stated = stated_gift_inputs(query)
    assert isinstance(stated, MissingInputs)
    assert any(label in item for item in stated.labels), stated.labels


@pytest.mark.parametrize('query', [
    '창업자금으로 아버지에게 5억 증여받으면 증여세 얼마?',
    '비상장 주식을 아들에게 3억 증여하면 증여세 얼마?',
    '아버지 사망 후 상속받은 3억이면 상속세 얼마야?',
    '증여세 얼마야?',
])
def test_unmodelled_or_unreadable_gifts_take_the_ordinary_path(query):
    assert stated_gift_inputs(query) is None


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator_and_its_assumptions(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    events = []
    result = await planner.run_tools_for_query(QUESTION, user_id=str(uuid4()), on_event=events.append)
    assert (result.tool, result.status) == ('gift', 'ok')
    context = result.calculation.context
    assert context.startswith('계산에 쓴 가정:')
    # 3억 - 5천만 = 2.5억 x 20% - 1천만 = 4천만, 신고세액공제 120만
    assert '- 증여세 과세표준: 250,000,000원' in context and '- 납부할 세액: 38,800,000원' in context
    assert [e['status'] for e in events] == ['running', 'ok']


@pytest.mark.asyncio
async def test_chat_asks_for_missing_facts_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('아버지한테 3억 증여받으면 증여세 얼마야?', user_id=str(uuid4()))
    assert (result.tool, result.status, result.error_code) == ('gift', 'needs_input', 'calculation_inputs_required')
    assert '미성년자' in result.context


@pytest.mark.asyncio
async def test_unmodelled_gift_goes_to_tool_selection(monkeypatch):
    select = AsyncMock(return_value=None)
    monkeypatch.setattr(planner, 'select_tool', select)
    await planner.run_tools_for_query('창업자금으로 아버지에게 5억 증여받으면 증여세 얼마?', user_id=str(uuid4()))
    select.assert_awaited_once()

"""VAT and penalty tax questions in chat: the calculators read the stated facts, ask for the facts that
decide the formula, and leave unmodelled cases to the ordinary path."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import penalty_tax as pt, vat
from app.services.calculator.penalty_inputs import MissingInputs as PenaltyMissing, stated_penalty_inputs
from app.services.calculator.vat_inputs import MissingInputs as VatMissing, stated_vat_inputs
from app.services.tools import planner
from tests.test_vat_penalty import penalty_params, vat_params


@pytest.fixture
def stored_figures(monkeypatch):
    async def load_vat(as_of=None):
        return vat_params()

    async def load_penalty(as_of=None):
        return penalty_params()
    monkeypatch.setattr(vat, 'load_parameters', load_vat)
    monkeypatch.setattr(pt, 'load_parameters', load_penalty)


@pytest.mark.parametrize('query, expected', [
    ('매출 1억 매입 6천만원, 일반과세 부가세 얼마 내야해?', {'sales': 100_000_000, 'purchases': 60_000_000, 'is_simplified': False}),
    ('간이과세자 식당인데 매출 6천만원, 카드매출 4,600만원이면 부가세 얼마?',
     {'is_simplified': True, 'business_type': '음식점업', 'card_sales': 46_000_000}),
    ('일반과세자인데 매출 2억, 매입 1억 2천만원, 카드 매출 1억, 예정고지 300만원이면 부가세 얼마?',
     {'card_sales': 100_000_000, 'prepaid_tax': 3_000_000}),
    ('법인 매출 3억, 매입 2억이면 부가세 얼마?', {'card_credit_eligible': False, 'is_simplified': False}),
])
def test_stated_vat_questions_are_read(query, expected):
    stated = stated_vat_inputs(query)
    assert not isinstance(stated, VatMissing) and stated is not None, stated
    assert {k: stated.params[k] for k in expected} == expected


@pytest.mark.parametrize('query, label', [
    ('매출 5천만원이면 부가세 얼마야?', '간이과세자'),
    ('간이과세자인데 매출 6천만원이면 부가세 얼마야?', '업종'),
])
def test_vat_facts_that_decide_the_formula_are_asked(query, label):
    stated = stated_vat_inputs(query)
    assert isinstance(stated, VatMissing) and any(label in item for item in stated.labels), stated


@pytest.mark.parametrize('query', [
    '음식점 일반과세자 매출 1억, 면세 농산물 3천만원이면 부가세 얼마?',
    '부동산 임대 보증금 5억, 월세 300만원이면 부가세 얼마?',
    '부가세 얼마야?',
])
def test_unmodelled_vat_questions_take_the_ordinary_path(query):
    assert stated_vat_inputs(query) is None


@pytest.mark.parametrize('query, expected', [
    ('미납 세액 1,000만원 무신고, 부정행위 없음, 지연 일수 0일 가산세 얼마나 나와?',
     {'unpaid_tax': 10_000_000, 'penalty_type': '무신고', 'is_negligent': False, 'days_late': 0}),
    ('종합소득세 500만원을 신고 안 하고 2개월 늦게 기한 후 신고하면 가산세 얼마?',
     {'penalty_type': '무신고', 'filed_within_months': 2, 'days_late': 60}),
    ('부가세 300만원을 덜 신고해서 5개월 뒤 수정신고하면 가산세는?', {'penalty_type': '과소신고', 'filed_within_months': 5}),
    ('세금 1000만원을 신고는 했는데 납부를 100일 늦게 하면 가산세 얼마?', {'penalty_type': '납부지연', 'days_late': 100}),
    ('이중장부로 세금 2천만원을 신고 안 했는데 1년 뒤 걸리면 가산세 얼마?', {'is_negligent': True, 'days_late': 360}),
])
def test_stated_penalty_questions_are_read(query, expected):
    stated = stated_penalty_inputs(query)
    assert not isinstance(stated, PenaltyMissing) and stated is not None, stated
    assert {k: stated.params[k] for k in expected} == expected


@pytest.mark.parametrize('query, label', [
    ('세금 1000만원 가산세 얼마야?', '무신고'),
    ('세금 1000만원을 신고 안 했으면 가산세 얼마야?', '며칠'),
])
def test_penalty_facts_that_decide_the_amount_are_asked(query, label):
    stated = stated_penalty_inputs(query)
    assert isinstance(stated, PenaltyMissing) and any(label in item for item in stated.labels), stated


@pytest.mark.asyncio
async def test_chat_answers_vat_with_the_calculator(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('간이과세자 식당인데 매출 6천만원, 카드매출 4,600만원이면 부가세 얼마?',
                                               user_id=str(uuid4()))
    assert (result.tool, result.status) == ('vat', 'ok')
    # 6천만 x 15% x 10% = 90만 - 카드 4,600만 x 1.3% = 59.8만
    assert '- 차감 납부할 세액: 302,000원' in result.calculation.context


@pytest.mark.asyncio
async def test_chat_answers_a_penalty_with_the_calculator(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('종합소득세 500만원을 신고 안 하고 2개월 늦게 기한 후 신고하면 가산세 얼마?',
                                               user_id=str(uuid4()))
    assert (result.tool, result.status) == ('penalty_tax', 'ok')
    # 무신고 100만 - 감면 30% = 70만, 납부지연 500만 x 0.022% x 60일 = 66,000
    assert '- 가산세 합계: 766,000원' in result.calculation.context

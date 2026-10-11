"""A property-sale tax question in chat: the capital gains calculator reads the stated facts,
asks for the facts that decide exemption, and leaves unmodelled cases to the ordinary path."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import capital_gains as cg
from app.services.calculator.capital_gains_inputs import MissingInputs, StatedInputs, stated_capital_gains_inputs
from app.services.tools import planner
from tests.test_capital_gains import params

QUESTION = '10억에 산 아파트를 15억에 팔면 양도소득세 얼마야? 1세대 1주택이고 7년 보유, 5년 거주했어'


@pytest.fixture
def stored_figures(monkeypatch):
    async def load(as_of=None):
        return params()
    monkeypatch.setattr(cg, 'load_parameters', load)


def test_a_spoken_sale_is_read_into_calculator_inputs():
    stated = stated_capital_gains_inputs(QUESTION)
    assert isinstance(stated, StatedInputs)
    assert stated.params == {'transfer_price': 1_500_000_000, 'acquisition_price': 1_000_000_000, 'expenses': 0,
                             'holding_years': 7, 'asset_type': '주택', 'is_one_home': True, 'residence_years': 5,
                             'acquired_in_adjusted_area': False, 'multi_home_surcharge': '없음',
                             'non_business_land': False, 'unregistered': False}
    assert any('필요경비' in a for a in stated.assumptions)


def test_labelled_amounts_and_land_are_read():
    stated = stated_capital_gains_inputs('토지 양도가액 3억, 취득가액 1억 5천만원, 필요경비 2,650만원, 보유기간 7년이면 양도세 얼마야?')
    assert stated.params['transfer_price'] == 300_000_000 and stated.params['acquisition_price'] == 150_000_000
    assert stated.params['expenses'] == 26_500_000 and stated.params['asset_type'] == '토지·건물'
    assert any('비사업용 토지' in a for a in stated.assumptions)


@pytest.mark.parametrize('query, label', [
    ('10억에 산 아파트를 15억에 팔면 양도세 얼마야? 7년 보유했어', '1세대 1주택 여부'),
    ('1주택인데 10억에 산 아파트를 15억에 팔면 양도세 얼마야?', '보유기간'),
    ('1주택인데 10억에 산 아파트를 15억에 팔면 양도세 얼마야? 7년 보유', '거주기간'),
    ('1주택인데 10억에 산 아파트를 15억에 팔면 양도세 얼마야? 7년 보유, 거주는 안 했어', '조정대상지역'),
    ('15억에 팔면 양도세 얼마야? 1주택, 7년 보유, 5년 거주', '취득가액'),
])
def test_facts_that_decide_the_tax_are_asked_not_assumed(query, label):
    stated = stated_capital_gains_inputs(query)
    assert isinstance(stated, MissingInputs)
    assert any(label in item for item in stated.labels), stated.labels


@pytest.mark.parametrize('query', [
    '비트코인을 1천만원에 사서 5천만원에 팔면 세금 얼마?',            # 가상자산은 양도소득이 아님
    '양도소득세 얼마야?',                                          # no sale price at all
    '아파트와 토지를 10억에 사서 15억에 팔면 양도세 얼마야?',      # two kinds of property
    '해외 아파트를 5억에 사서 8억에 팔면 양도세 얼마야?',
])
def test_unmodelled_or_unreadable_sales_take_the_ordinary_path(query):
    assert stated_capital_gains_inputs(query) is None


@pytest.mark.parametrize('query, expected', [
    ('2주택인데 비조정지역 아파트를 5억에 사서 8억에 팔면 양도세 얼마? 6년 보유', {'asset_type': '주택', 'multi_home_surcharge': '없음'}),
    ('3주택인데 조정대상지역 아파트를 5억에 사서 8억에 팔면 양도세 얼마? 6년 보유, 중과 대상이야', {'multi_home_surcharge': '3주택이상'}),
    ('분양권을 1억 6천만원에 사서 2억 4천만원에 팔면 양도세 얼마야? 2년 보유', {'asset_type': '분양권'}),
    ('재개발 입주권을 2억에 사서 4억에 팔면 양도세 얼마? 3년 보유', {'asset_type': '조합원입주권', 'pre_approval_gain': 0}),
    ('비사업용 토지를 5천만원에 사서 2억 5천만원에 팔면 양도세 얼마? 1년 보유', {'non_business_land': True}),
    ('골프회원권을 1억에 사서 2억에 팔면 양도세 얼마?', {'asset_type': '기타자산'}),
    ('해외주식을 5천만원에 사서 1억에 팔면 양도세 얼마?', {'asset_type': '주식', 'stock_market': '국외'}),
    ('비상장 주식 대주주인데 5억에 사서 10억에 팔면 양도세 얼마? 10년 보유', {'stock_market': '국내비상장', 'major_shareholder': True}),
    ('상장주식 소액주주인데 1억에 사서 1억 5천만원에 팔면 양도세 얼마?', {'stock_market': '국내상장', 'major_shareholder': False}),
    ('파생상품 3천만원에 사서 6천만원에 팔면 양도세 얼마?', {'asset_type': '파생상품'}),
])
def test_other_assets_are_read(query, expected):
    stated = stated_capital_gains_inputs(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params.get(k, 0) for k in expected} == expected


@pytest.mark.parametrize('query, label', [
    ('2주택인데 5억에 산 아파트를 8억에 팔면 양도세 얼마? 6년 보유', '조정대상지역'),
    ('2주택인데 조정대상지역 아파트를 5억에 사서 8억에 팔면 양도세 얼마? 6년 보유', '중과 대상'),
    ('상장주식을 1억에 사서 1억 5천만원에 팔면 양도세 얼마?', '대주주'),
    ('주식을 1억에 사서 2억에 팔면 양도세 얼마야?', '해외주식'),
    ('원조합원인데 재개발 입주권을 2억에 사서 4억에 팔면 양도세 얼마? 6년 보유', '관리처분계획인가 전'),
])
def test_facts_that_set_the_rate_are_asked(query, label):
    stated = stated_capital_gains_inputs(query)
    assert isinstance(stated, MissingInputs) and any(label in item for item in stated.labels), stated


def test_a_previous_turn_completes_the_facts():
    history = [{'role': 'user', 'content': '1세대 1주택이고 아파트를 10억에 샀어. 7년 보유, 5년 거주했어'}]
    stated = stated_capital_gains_inputs('15억에 팔면 양도세 얼마야?', history)
    assert stated.params['transfer_price'] == 1_500_000_000 and stated.params['residence_years'] == 5


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator_and_its_assumptions(monkeypatch, stored_figures):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    events = []
    result = await planner.run_tools_for_query(QUESTION, user_id=str(uuid4()), on_event=events.append)
    assert (result.tool, result.status) == ('capital_gains', 'ok')
    context = result.calculation.context
    assert context.startswith('계산에 쓴 가정:')
    # 차익 5억, 과세 비율 3/15 -> 1억, 공제 48% 안분 4,800만 -> 소득금액 5,200만 - 250만 = 4,950만 x 15% - 126만
    assert '- 과세표준: 49,500,000원' in context
    assert '산출세액(기본세율 15%): 6,165,000원' in context
    assert [e['status'] for e in events] == ['running', 'ok']


@pytest.mark.asyncio
async def test_chat_asks_for_missing_facts_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(planner, 'select_tool', AsyncMock(side_effect=AssertionError('no selection needed')))
    result = await planner.run_tools_for_query('10억에 산 아파트를 15억에 팔면 양도세 얼마야? 7년 보유했어', user_id=str(uuid4()))
    assert (result.tool, result.status, result.error_code) == ('capital_gains', 'needs_input', 'calculation_inputs_required')
    assert '1세대 1주택 여부' in result.context


@pytest.mark.asyncio
async def test_unmodelled_sale_goes_to_tool_selection(monkeypatch):
    select = AsyncMock(return_value=None)
    monkeypatch.setattr(planner, 'select_tool', select)
    await planner.run_tools_for_query('해외 아파트를 5억에 사서 8억에 팔면 양도세 얼마야?', user_id=str(uuid4()))
    select.assert_awaited_once()

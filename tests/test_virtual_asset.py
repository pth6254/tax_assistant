"""Virtual asset income: 소득세법 제37조 제5항·제64조의3 제2항 (2027-01-01 시행). No official worked example is
published yet, so the figures are checked against the statute's formula."""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import virtual_asset as va
from app.services.calculator.errors import CalculationError
from app.services.calculator.virtual_asset_inputs import MissingInputs, StatedInputs, stated_virtual_asset_inputs
from app.services.tools import planner
from tests.test_calculator import _patch_repository


def params():
    return va.Parameters(rate=Decimal("0.2"), basic_deduction=2_500_000, local_ratio=Decimal("0.1"))


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


def test_gain_above_the_deduction_is_taxed_at_twenty_percent():
    result = va.compute(params=params(), transfer_price=50_000_000, acquisition_price=10_000_000, expenses=500_000)
    # (5천만 - 1천만 - 50만 - 250만) x 20% = 7,400,000
    assert result.decided_tax == 7_400_000 and step(result, "지방소득세") == 740_000


def test_coins_held_before_2027_use_the_higher_of_cost_and_year_end_price():
    result = va.compute(params=params(), transfer_price=50_000_000, acquisition_price=10_000_000,
                        held_before_2027=True, value_2026_end=40_000_000)
    assert step(result, "취득가액(실제") == 40_000_000 and result.decided_tax == 1_500_000


def test_sales_before_2027_are_not_taxed_but_show_the_future_tax():
    result = va.compute(params=params(), transfer_price=50_000_000, acquisition_price=10_000_000, taxed=False)
    assert result.decided_tax == 0 and step(result, "같은 조건으로 2027년 이후") == 7_500_000


def test_year_end_price_without_holding_is_rejected():
    with pytest.raises(CalculationError):
        va.compute(params=params(), transfer_price=1, acquisition_price=1, value_2026_end=1)


@pytest.mark.asyncio
async def test_calculate_switches_on_the_2027_start():
    with _patch_repository(va):
        before = await va.calculate(transfer_price=50_000_000, acquisition_price=10_000_000, as_of=date(2026, 10, 11))
        after = await va.calculate(transfer_price=50_000_000, acquisition_price=10_000_000, as_of=date(2027, 3, 1))
    assert (before.final_tax, after.final_tax) == (0, 7_500_000)


@pytest.mark.parametrize("query, expected", [
    ("비트코인을 1천만원에 사서 5천만원에 팔면 세금 얼마?", {"transfer_price": 50_000_000, "held_before_2027": False}),
    ("2024년에 이더리움을 2천만원에 샀는데 2026년말 시가 3천만원이고 5천만원에 팔면 세금 얼마?",
     {"held_before_2027": True, "value_2026_end": 30_000_000}),
])
def test_coin_questions_are_read(query, expected):
    stated = stated_virtual_asset_inputs(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params[k] for k in expected} == expected


def test_missing_cost_is_asked_and_lending_is_left_alone():
    assert isinstance(stated_virtual_asset_inputs("코인을 5천만원에 팔면 세금 얼마야?"), MissingInputs)
    assert stated_virtual_asset_inputs("코인 스테이킹 이자 500만원이면 세금 얼마?") is None


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator(monkeypatch):
    async def load(as_of=None):
        return params(), False
    monkeypatch.setattr(va, "load_parameters", load)
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no selection needed")))
    result = await planner.run_tools_for_query("비트코인을 1천만원에 사서 5천만원에 팔면 세금 얼마?", user_id=str(uuid4()))
    assert (result.tool, result.status) == ("virtual_asset", "ok")
    assert "2027년 이후 양도하면 낼 세액(20%): 7,500,000원" in result.calculation.context

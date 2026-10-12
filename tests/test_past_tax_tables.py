"""Rates in force from 2021-01-01 (Alembic 20261012_0022) and the rules that did not exist then."""
import importlib.util
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import capital_gains as cg, income_tax as it, vat
from app.services.calculator.errors import CalculationError
from tests.test_capital_gains import params as cg_params
from tests.test_income_tax import kinds, params as income_params
from tests.test_vat_penalty import vat_params

SPEC = importlib.util.spec_from_file_location(
    "past_tables", Path(__file__).parents[1] / "alembic" / "versions" / "20261012_0022_past_tax_tables.py")
PAST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAST)


@pytest.mark.parametrize("bands", [PAST.OLD_BASIC, PAST.NEW_BASIC, PAST.INHERITANCE])
def test_each_progressive_constant_continues_the_band_below(bands):
    # rate x 경계 - 누진공제 must be equal from both sides of every boundary.
    for (low, _, rate, deduction), (_, _, prev_rate, prev_deduction) in zip(bands[1:], bands):
        assert Decimal(rate) * low - deduction == Decimal(prev_rate) * low - prev_deduction


def test_the_2021_table_gives_the_statute_amounts():
    # 제55조(2021-01-01): 8,800만원 초과 1,590만원+35%, 10억원 초과 3억8,460만원+45%
    tax = lambda base: next(Decimal(r) * base - d for low, high, r, d in reversed(PAST.OLD_BASIC) if base > low)
    assert tax(100_000_000) == 15_900_000 + Decimal("0.35") * 12_000_000
    assert tax(2_000_000_000) == 384_600_000 + Decimal("0.45") * 1_000_000_000


def test_a_house_held_one_to_two_years_before_june_2021_pays_the_basic_rate():
    old = replace(cg_params(), short_rates={**cg_params().short_rates, ("주택", 1): Decimal(0)})
    result = cg.compute(params=old, transfer_price=600_000_000, acquisition_price=500_000_000, holding_years=1)
    basic, _ = cg.apply_progressive_tax(result.taxable_income, old.brackets)
    assert result.calculated_tax == basic
    assert not any("0%" in note for note in result.notes)


def test_a_large_private_pension_before_2023_is_taxed_only_comprehensively():
    without_option = replace(income_params(), kinds={**kinds(), "사적연금_분리과세율": None})
    result = it.compute(params=without_option, private_pension=20_000_000, pension_age=65)
    assert not any("사적연금 분리과세 세액" in label for label, _ in result.steps)
    with_option = it.compute(params=income_params(), private_pension=20_000_000, pension_age=65)
    assert with_option.decided_tax <= result.decided_tax


def test_a_simplified_taxpayer_before_the_2021_reform_is_not_computed():
    before = vat_params(simple_rates=None, simple_input_rate=None)
    with pytest.raises(CalculationError) as error:
        vat.compute(params=before, sales=50_000_000, is_simplified=True, business_type="소매업")
    assert error.value.code == "missing_tax_data"
    assert vat.compute(params=before, sales=100_000_000, purchases=60_000_000).decided_tax == 4_000_000

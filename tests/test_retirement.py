"""Retirement income tax against the National Tax Service's worked example, plus the chat reader."""
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.calculator import retirement as rt
from app.services.calculator.errors import CalculationError
from app.services.calculator.retirement_inputs import MissingInputs, StatedInputs, stated_retirement_inputs
from app.services.tools import planner
from tests.test_calculator import _BRACKETS, _patch_repository

DATA = json.loads((Path(__file__).parent / "data" / "nts_retirement.json").read_text(encoding="utf-8"))
CURRENT = [[5, 0, 1_000_000, 0], [10, 5_000_000, 2_000_000, 5], [20, 15_000_000, 2_500_000, 10],
           [None, 40_000_000, 3_000_000, 20]]
OLD = [[5, 0, 300_000, 0], [10, 1_500_000, 500_000, 5], [20, 4_000_000, 800_000, 10], [None, 12_000_000, 1_200_000, 20]]


def params(tiers=CURRENT):
    band = lambda rows: [{"bracket_from": a, "rate": Decimal(str(r)), "progressive_deduction": d} for a, r, d in rows]
    return rt.Parameters(
        service_tiers=tiers,
        converted_bands=band([(0, "1.0", 0), (8_000_000, "0.6", -3_200_000), (70_000_000, "0.55", -6_700_000),
                              (100_000_000, "0.45", -16_700_000), (300_000_000, "0.35", -46_700_000)]),
        brackets=[{**b, "rate": Decimal(str(b["rate"]))} for b in _BRACKETS[("소득세", "default")]],
        local_ratio=Decimal("0.1"))


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


STEP = {"service": "근속연수공제", "converted": "환산급여(", "converted_deduction": "환산급여공제",
        "taxable": "퇴직소득 과세표준", "converted_tax": "환산산출세액"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_the_published_example(case):
    result = rt.compute(params=params(), **case["inputs"])
    for key, expected in case["expected"].items():
        actual = result.calculated_tax if key == "calculated_tax" else step(result, STEP[key])
        assert actual == expected, (key, actual, expected)


@pytest.mark.parametrize("years, current, old", [(3, 3_000_000, 900_000), (8, 11_000_000, 3_000_000),
                                                 (25, 55_000_000, 18_000_000)])
def test_service_deduction_tables_before_and_after_2023(years, current, old):
    assert rt.service_deduction(params(), years) == current
    assert rt.service_deduction(params(OLD), years) == old


def test_converted_pay_deduction_bands():
    # 환산급여 3억 2천만: 1억5,170만 + 2천만 x 35% = 1억5,870만
    result = rt.compute(params=params(), retirement_pay=400_000_000, service_years=15)
    assert step(result, "환산급여(") == (400_000_000 - 27_500_000) * 12 // 15
    assert step(result, "환산급여공제") == int(Decimal(298_000_000) * Decimal("0.45")) + 16_700_000


def test_small_pay_below_the_service_deduction_has_no_tax():
    result = rt.compute(params=params(), retirement_pay=10_000_000, service_years=10)
    assert result.calculated_tax == 0 and step(result, "근속연수공제") == 10_000_000


def test_local_tax_is_shown_apart_and_zero_years_is_invalid():
    result = rt.compute(params=params(), retirement_pay=100_000_000, service_years=20, prepaid_tax=1_120_000)
    assert step(result, "지방소득세") == 112_000 and step(result, "차감 납부할 세액") == 0
    with pytest.raises(CalculationError):
        rt.compute(params=params(), retirement_pay=1, service_years=0)


@pytest.mark.asyncio
async def test_calculate_reads_every_statutory_figure_from_the_database():
    with _patch_repository(rt):
        result = await rt.calculate(retirement_pay=100_000_000, service_years=20)
    assert result.final_tax == 1_120_000


@pytest.mark.parametrize("query, expected", [
    ("퇴직금 1억 받으면 퇴직소득세 얼마야? 20년 근무했어", {"retirement_pay": 100_000_000, "service_years": 20}),
    ("근속기간 9년 3개월, 퇴직금 5천만원이면 세금 얼마?", {"retirement_pay": 50_000_000, "service_years": 10}),
    ("18개월 다닌 회사 퇴직금 300만원이면 세금 얼마야?", {"service_years": 2}),
])
def test_retirement_questions_are_read(query, expected):
    stated = stated_retirement_inputs(query)
    assert isinstance(stated, StatedInputs), stated
    assert {k: stated.params[k] for k in expected} == expected


def test_missing_years_are_asked_and_pension_account_transfers_are_read():
    assert isinstance(stated_retirement_inputs("퇴직금 1억 받으면 세금 얼마야?"), MissingInputs)
    whole = stated_retirement_inputs("퇴직금 1억을 IRP로 옮겨 연금으로 받으면 세금 얼마야? 20년 근무")
    assert whole.params["pension_transfer"] == 100_000_000
    part = stated_retirement_inputs("퇴직금 1억원 근속 20년인데 5천만원을 IRP로 이체하면 퇴직소득세 얼마야?")
    assert (part.params["service_years"], part.params["pension_transfer"]) == (20, 50_000_000)
    assert stated_retirement_inputs("퇴직금 1억원, 20년 근무")
    unknown = stated_retirement_inputs("퇴직금 1억원 20년 근무했는데 일부를 연금계좌로 옮기면 세금 얼마야?")
    assert isinstance(unknown, MissingInputs) and "연금계좌" in unknown.labels[0]


@pytest.mark.asyncio
async def test_chat_answers_with_the_calculator(monkeypatch):
    async def load(as_of=None):
        return params()
    monkeypatch.setattr(rt, "load_parameters", load)
    monkeypatch.setattr(planner, "select_tool", AsyncMock(side_effect=AssertionError("no selection needed")))
    result = await planner.run_tools_for_query("퇴직금 1억 받으면 퇴직소득세 얼마야? 20년 근무했어", user_id=str(uuid4()))
    assert (result.tool, result.status) == ("retirement", "ok")
    assert "- 퇴직소득 산출세액(환산산출세액 / 12 x 근속연수): 1,120,000원" in result.calculation.context

"""The financial income calculator through the API, the engine and the chat input checks."""
from decimal import Decimal

import pytest

from app.services.calculator import engine, financial_income_tax as fit
from app.services.tools.policy import check_proposal, financial_income_scope, input_proof
from app.services.tools.registry import TOOL_SCHEMAS

# Current figures as stored: 2024~ brackets (소득세법 제55조), gross-up 10% (제17조 제3항).
BRACKETS_2024 = [(0, "0.06", 0), (14_000_000, "0.15", 1_260_000), (50_000_000, "0.24", 5_760_000),
                 (88_000_000, "0.35", 15_440_000), (150_000_000, "0.38", 19_940_000),
                 (300_000_000, "0.40", 25_940_000), (500_000_000, "0.42", 35_940_000),
                 (1_000_000_000, "0.45", 65_940_000)]


def current_parameters():
    return fit.Parameters(
        threshold=20_000_000, withholding_rate=Decimal("0.14"), non_business_rate=Decimal("0.25"),
        gross_up_rate=Decimal("0.10"),
        brackets=[{"bracket_from": lower, "rate": Decimal(rate), "progressive_deduction": deduction}
                  for lower, rate, deduction in BRACKETS_2024],
        effective_dates=("2013-01-01", "2024-01-01"), sources=("소득세법 제129조", "소득세법 제14조"))


@pytest.fixture
def stored_parameters(monkeypatch):
    async def load(as_of=None):
        return current_parameters()
    monkeypatch.setattr(fit, "load_parameters", load)


def test_requires_login(client):
    assert client.post("/api/calculator/financial-income-tax", json={"interest_income": 1}).status_code == 401


def test_rejects_negative_or_mistyped_amounts(client, auth_cookie):
    for body in ({"interest_income": -1}, {"interest_income": "1억"}):
        assert client.post("/api/calculator/financial-income-tax", json=body, cookies=auth_cookie).status_code == 422


def test_interest_of_100_million_with_the_basic_deduction(client, auth_cookie, stored_parameters):
    response = client.post("/api/calculator/financial-income-tax", cookies=auth_cookie,
                           json={"interest_income": 100_000_000, "income_deductions": 1_500_000})
    assert response.status_code == 200
    body = response.json()
    steps = {step["label"]: step["amount"] for step in body["steps"]}
    # (80M - 1.5M) x 24% - 5.76M + 20M x 14% = 15.88M  vs  100M x 14% = 14M
    assert steps["① 종합과세 방식 산출세액"] == 15_880_000
    assert steps["② 원천징수세율 방식 산출세액"] == 14_000_000
    assert body["calculated_tax"] == body["final_tax"] == 15_880_000
    assert steps["기납부세액(법정 원천징수세율로 추정)"] == 14_000_000
    assert steps["차감 납부할 세액"] == 1_880_000
    assert body["tax_type"] == "소득세(금융소득 종합과세)"
    assert any("비교과세" in note for note in body["notes"]) and any("지방소득세" in note for note in body["notes"])


def test_no_financial_income_is_refused_with_a_reason(client, auth_cookie, stored_parameters):
    response = client.post("/api/calculator/financial-income-tax", cookies=auth_cookie, json={"other_income": 1})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_engine_context_carries_scope_notes(stored_parameters):
    run = await engine.run_calculation("financial_income_tax", {"interest_income": 30_000_000})
    assert "- 참고: " in run.context and "출자공동사업자" in run.context
    assert "financial_income_tax" in TOOL_SCHEMAS


def test_withholding_status_is_read_without_mistaking_the_negative_form():
    assert input_proof("withheld", True, ["국내에서 원천징수된 이자입니다"]) == "원천징수된"
    assert input_proof("withheld", False, ["국외에서 받아 원천징수되지 않은 이자입니다"]) == "원천징수되지"
    assert input_proof("withheld", True, ["국외에서 받아 원천징수되지 않은 이자입니다"]) is None


def test_fully_stated_inputs_pass_the_chat_check():
    query = ("이자소득 1억원, 비영업대금 0원, 배당 0원, 외국법인 배당 0원, 다른 소득 0원, 소득공제 150만원, "
             "원천징수된 소득입니다. 금융소득 종합과세 세금 계산해줘")
    params = {"interest_income": 100_000_000, "non_business_interest": 0, "dividend_gross_up": 0,
              "dividend_other": 0, "other_income": 0, "income_deductions": 1_500_000, "withheld": True}
    allowed, reason, _ = check_proposal("financial_income_tax", params, query, [], calculation_intent=True)
    assert allowed, reason
    # An unstated default is not assumed.
    allowed, reason, _ = check_proposal("financial_income_tax", params, "이자소득 1억원 금융소득 세금 계산해줘", [],
                                        calculation_intent=True)
    assert not allowed and reason.startswith("unconfirmed_inputs:")


def test_financial_follow_up_keeps_its_scope():
    history = [{"role": "user", "content": "금융소득 1억이면 세금 얼마야?"}]
    assert financial_income_scope("이자 1억 5천이면?", history)
    assert not financial_income_scope("양도소득세는?", history)

"""
test_calculator_engine.py — 계산기 챗봇 연동 엔진 단위 테스트

LLM 호출은 mock 처리. 게이트/파싱/검증/디스패치/포맷 로직을 검증한다.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.calculator import CalculationResult, TaxStep
from app.services.calculator.engine import (
    extract_calculation_request,
    format_calculation_context,
    has_calculation_intent,
    run_calculation_for_query,
)


# ── has_calculation_intent (키워드 게이트) ───────────────────────

@pytest.mark.parametrize("query", [
    "연소득 5천만원 프리랜서 세금 얼마야?",
    "10억짜리 아파트 팔면 양도세 계산해줘",
    "아버지한테 3억 증여받으면 세금 얼마나 나와?",
    "상속재산 15억이면 상속세 얼마 내야 해?",
])
def test_calculation_intent_detected(query):
    assert has_calculation_intent(query) is True


@pytest.mark.parametrize("query", [
    "경정청구 기한은 얼마나 되나요?",        # 계산 의도 단어 있지만 금액 없음
    "간이과세자의 부가가치세 신고 기준은?",   # 금액도 의도도 없음
    "소득세법 제55조 내용 알려줘",           # 숫자 있지만 계산 의도 없음
])
def test_calculation_intent_not_detected(query):
    assert has_calculation_intent(query) is False


# ── 실제 추출 파이프라인의 JSON 처리 ─────────────────────────────

@pytest.mark.asyncio
async def test_extraction_plain_json():
    raw = '{"tool": "income_tax", "params": {"income": 50000000}}'
    with patch("app.services.calculator.engine.call_llm", AsyncMock(return_value=raw)):
        assert await extract_calculation_request("소득 5천만원") == ("income_tax", {"income": 50000000})


@pytest.mark.asyncio
async def test_extraction_json_in_code_fence():
    raw = '```json\n{"tool": "gift", "params": {"gift_amount": 300000000}}\n```'
    with patch("app.services.calculator.engine.call_llm", AsyncMock(return_value=raw)):
        assert await extract_calculation_request("증여 3억") == ("gift", {"gift_amount": 300000000})


@pytest.mark.asyncio
async def test_extraction_json_after_think_block():
    raw = '<think>어떤 계산기...</think>{"tool": "none"}'
    with patch("app.services.calculator.engine.call_llm", AsyncMock(return_value=raw)):
        assert await extract_calculation_request("안녕하세요") is None


@pytest.mark.asyncio
async def test_extraction_invalid_returns_none():
    with patch("app.services.calculator.engine.call_llm", AsyncMock(return_value="죄송합니다, 판단할 수 없습니다.")):
        assert await extract_calculation_request("계산해줘") is None


# ── format_calculation_context ───────────────────────────────────

def test_format_includes_steps_and_articles():
    result = CalculationResult(
        tax_type="소득세",
        steps=[TaxStep(label="과세표준", amount=48500000), TaxStep(label="결정세액", amount=5895000)],
        taxable_income=48500000,
        calculated_tax=6015000,
        final_tax=5895000,
        effective_rate=0.1179,
        source_articles=["소득세법 제55조"],
    )
    text = format_calculation_context(result)
    assert "세목: 소득세" in text
    assert "과세표준: 48,500,000원" in text
    assert "실효세율: 11.79%" in text
    assert "소득세법 제55조" in text


# ── run_calculation_for_query (전체 흐름, LLM/계산기 mock) ────────

def _dummy_result() -> CalculationResult:
    return CalculationResult(
        tax_type="소득세", steps=[TaxStep(label="결정세액", amount=5895000)],
        taxable_income=48500000, calculated_tax=6015000, final_tax=5895000,
        effective_rate=0.1179, source_articles=["소득세법 제55조"],
    )


@pytest.mark.asyncio
async def test_run_calculation_full_flow():
    with (
        patch(
            "app.services.calculator.engine.extract_calculation_request",
            AsyncMock(return_value=("income_tax", {"income": 50000000})),
        ),
        patch(
            "app.services.calculator.engine.income_tax.calculate",
            AsyncMock(return_value=_dummy_result()),
        ) as mock_calc,
    ):
        run = await run_calculation_for_query("연소득 5천만원 세금 얼마야?")
    assert run is not None
    assert "소득세법 제55조" in run.context
    assert run.tool == "income_tax"
    assert run.params == {
        "income": 50000000, "expense": 0,
        "personal_deduction_count": 1, "other_deductions": 0,
    }
    mock_calc.assert_awaited_once_with(
        income=50000000, expense=0, personal_deduction_count=1, other_deductions=0
    )


@pytest.mark.asyncio
async def test_run_calculation_skips_without_intent():
    """게이트 불통과 시 LLM 추출 자체를 호출하지 않는다."""
    with patch(
        "app.services.calculator.engine.extract_calculation_request", AsyncMock()
    ) as mock_extract:
        text = await run_calculation_for_query("경정청구 기한은 얼마나 되나요?")
    assert text is None
    mock_extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_calculation_invalid_params_returns_none():
    """스키마 검증 실패(income 누락) 시 None — 채팅은 RAG로 정상 진행."""
    with patch(
        "app.services.calculator.engine.extract_calculation_request",
        AsyncMock(return_value=("income_tax", {"expense": 1000})),
    ):
        text = await run_calculation_for_query("세금 5천만원 얼마 계산해줘")
    assert text is None


@pytest.mark.asyncio
async def test_run_calculation_extraction_none_returns_none():
    with patch(
        "app.services.calculator.engine.extract_calculation_request",
        AsyncMock(return_value=None),
    ):
        text = await run_calculation_for_query("세금 5천만원 얼마 계산해줘")
    assert text is None


# ── vat / penalty_tax 도구 라우팅 ─────────────────────────────────

def _dummy_vat_result() -> CalculationResult:
    return CalculationResult(
        tax_type="부가가치세", steps=[TaxStep(label="차가감 납부(환급)세액", amount=4000000)],
        taxable_income=100000000, calculated_tax=10000000, final_tax=4000000,
        effective_rate=0.04, source_articles=["부가가치세법 제37조"],
    )


@pytest.mark.asyncio
async def test_run_calculation_routes_to_vat():
    with (
        patch(
            "app.services.calculator.engine.extract_calculation_request",
            AsyncMock(return_value=("vat", {"sales": 100000000, "purchases": 60000000})),
        ),
        patch(
            "app.services.calculator.engine.vat.calculate",
            AsyncMock(return_value=_dummy_vat_result()),
        ) as mock_calc,
    ):
        run = await run_calculation_for_query("매출 1억 매입 6천만원인데 부가세 얼마 내야해?")
    assert run is not None
    assert run.tool == "vat"
    mock_calc.assert_awaited_once_with(
        sales=100000000, purchases=60000000, exempt_sales=0,
        is_simplified=False, business_type="소매업",
    )


def _dummy_penalty_result() -> CalculationResult:
    return CalculationResult(
        tax_type="가산세", steps=[TaxStep(label="납부할 총액(본세+가산세)", amount=12000000)],
        taxable_income=10000000, calculated_tax=2000000, final_tax=12000000,
        effective_rate=0.2, source_articles=["국세기본법 제47조의2"],
    )


@pytest.mark.asyncio
async def test_run_calculation_routes_to_penalty_tax():
    with (
        patch(
            "app.services.calculator.engine.extract_calculation_request",
            AsyncMock(return_value=("penalty_tax", {"unpaid_tax": 10000000, "penalty_type": "무신고"})),
        ),
        patch(
            "app.services.calculator.engine.penalty_tax.calculate",
            AsyncMock(return_value=_dummy_penalty_result()),
        ) as mock_calc,
    ):
        run = await run_calculation_for_query("종합소득세 1,000만원 무신고했는데 가산세 얼마나 나와?")
    assert run is not None
    assert run.tool == "penalty_tax"
    mock_calc.assert_awaited_once_with(
        unpaid_tax=10000000, penalty_type="무신고", is_negligent=False, days_late=0,
    )

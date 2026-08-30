"""
services/calculator/engine.py — 채팅 질문 → 세금 계산기 자동 연동 엔진

질문에서 계산 의도를 감지하면 LLM으로 계산기 종류·입력값을 추출하고,
해당 계산기를 실행하여 계산 과정과 근거 조문을 LLM 컨텍스트 문자열로 반환한다.

흐름:
  has_calculation_intent(query)      키워드 게이트 (LLM 호출 없음)
  extract_calculation_request(query) LLM으로 {"tool": ..., "params": {...}} 추출
  run_calculation_for_query(query)   위 두 단계 + 계산 실행 + 컨텍스트 포맷 (공개 진입점)
"""
import json
import logging
import re
from dataclasses import dataclass

from pydantic import ValidationError

from config import CHAT_MODEL
from app.schemas.calculator import (
    CalculationResult,
    CapitalGainsRequest,
    GiftTaxRequest,
    IncomeTaxRequest,
    InheritanceRequest,
    PenaltyTaxRequest,
    VatRequest,
)
from app.services.calculator import capital_gains, gift_tax, income_tax, inheritance, penalty_tax, vat
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

# Qwen3 계열은 options.think=False가 무시되는 경우가 있어 /no_think 접두사 병행
# (chat_service._QWEN3_NO_THINK_PREFIX와 동일한 대응)
_NO_THINK_PREFIX = "/no_think\n\n" if "qwen3" in CHAT_MODEL.lower() else ""

# 계산기 도구 정의: 이름 → (요청 스키마, 계산기 모듈)
# 함수가 아닌 모듈을 저장해 호출 시점에 calculate를 찾는다 (테스트 patch 가능)
_TOOLS = {
    "income_tax":    (IncomeTaxRequest,    income_tax),
    "capital_gains": (CapitalGainsRequest, capital_gains),
    "inheritance":   (InheritanceRequest,  inheritance),
    "gift":          (GiftTaxRequest,      gift_tax),
    "vat":           (VatRequest,          vat),
    "penalty_tax":   (PenaltyTaxRequest,   penalty_tax),
}

# 금액 표현: 숫자 또는 한글 단위(억/천만/백만/만원)
_AMOUNT_RE = re.compile(r"\d|[일이삼사오육칠팔구십백천]+\s*(?:억|천만|백만|만\s*원)")
# 계산 의도 키워드
_INTENT_RE = re.compile(r"얼마|계산|세액|세금.{0,6}(?:나오|내야|납부|부과)|내야\s*(?:하|할|되)")

_EXTRACT_PROMPT = (
    "사용자의 세무 질문에서 세금 계산기 실행에 필요한 정보를 추출하여 JSON만 출력하라.\n\n"
    "## 사용 가능한 계산기 (tool)\n"
    "1. income_tax — 종합소득세 (개인·프리랜서·사업자의 연소득)\n"
    "   params: income(총수입, 원), expense(필요경비, 기본 0), "
    "personal_deduction_count(본인 포함 부양가족 수, 기본 1), other_deductions(기타 소득공제, 기본 0)\n"
    "2. capital_gains — 양도소득세 (부동산 등 자산 양도)\n"
    "   params: transfer_price(양도가액), acquisition_price(취득가액), expenses(필요경비, 기본 0), "
    "holding_years(보유 연수, 기본 0), is_one_home(1세대 1주택 여부, 기본 false)\n"
    "3. inheritance — 상속세\n"
    "   params: estate_value(상속재산), debts(채무, 기본 0), "
    "spouse_inheritance(배우자 상속액, 기본 0), children_count(자녀 수, 기본 0)\n"
    "4. gift — 증여세\n"
    "   params: gift_amount(증여액), relation(배우자|직계존비속|기타친족|기타, 기본 기타), "
    "is_minor(수증자 미성년 여부, 기본 false), prior_gifts_10y(10년 내 기증여액, 기본 0)\n"
    "5. vat — 부가가치세 (사업자 매출·매입)\n"
    "   params: sales(매출액), purchases(매입액, 기본 0), exempt_sales(영세율·면세 매출, 기본 0), "
    "is_simplified(간이과세자 여부, 기본 false), business_type(업종: 소매업|음식점업|제조업|숙박업|건설업|서비스업|부동산임대업, 기본 소매업)\n"
    "6. penalty_tax — 가산세 (무신고·과소신고·납부지연)\n"
    "   params: unpaid_tax(무신고·과소신고·미납 세액), "
    "penalty_type(무신고|과소신고|납부지연, 기본 무신고), "
    "is_negligent(부정행위 여부, 기본 false), days_late(납부지연 시 연체일수, 기본 0)\n\n"
    "## 규칙\n"
    "- 금액은 원 단위 정수로 변환 (예: 5천만원 → 50000000, 3억 → 300000000)\n"
    "- 질문에 없는 파라미터는 생략 (기본값 사용)\n"
    "- 계산에 필요한 핵심 금액이 없거나 세금 계산 질문이 아니면 {\"tool\": \"none\"}\n"
    "- 자녀에게 증여 → relation: 직계존비속, 부모→자녀 상속·증여 모두 직계존비속\n"
    "- '신고 안 했다/무신고'는 penalty_type: 무신고, '적게 신고했다/과소신고'는 과소신고, "
    "'늦게 냈다/기한 넘겨 납부'는 납부지연\n\n"
    '출력 형식 (JSON만): {"tool": "income_tax", "params": {"income": 50000000}}\n'
    "- <think> 태그 내용은 출력하지 말 것\n"
)


def has_calculation_intent(query: str) -> bool:
    """금액 표현 + 계산 의도 키워드가 모두 있을 때만 True (LLM 호출 게이트)."""
    return bool(_AMOUNT_RE.search(query)) and bool(_INTENT_RE.search(query))


def _parse_extraction_json(raw: str) -> dict | None:
    """LLM 응답에서 JSON 오브젝트를 추출한다."""
    text = raw.split("</think>")[-1].strip()
    fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    candidate = fence.group(1).strip() if fence else text
    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def extract_calculation_request(query: str) -> tuple[str, dict] | None:
    """LLM으로 계산기 종류와 입력값을 추출한다. 대상 아님/실패 시 None."""
    try:
        raw = await call_llm(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": _NO_THINK_PREFIX + query},
            ],
            temperature=0.0,
            num_predict=400,
        )
    except Exception as e:
        logger.warning("[CALC] 파라미터 추출 LLM 호출 실패: %s", e)
        return None

    data = _parse_extraction_json(raw)
    if not data:
        logger.warning("[CALC] 추출 응답 JSON 파싱 실패: %.100s", raw)
        return None

    tool = data.get("tool", "none")
    if tool not in _TOOLS:
        return None
    params = data.get("params", {})
    return (tool, params) if isinstance(params, dict) else None


@dataclass
class CalcRun:
    """계산기 실행 결과 — LLM 컨텍스트 + 프론트엔드 왕복 연결(계산기 화면 프리필)용 메타데이터."""
    context: str
    tool: str
    params: dict


def format_calculation_context(result: CalculationResult) -> str:
    """계산 결과를 LLM 컨텍스트 문자열로 포맷한다."""
    lines = [f"세목: {result.tax_type}"]
    lines += [f"- {s.label}: {s.amount:,}원" for s in result.steps]
    lines.append(f"- 실효세율: {result.effective_rate * 100:.2f}%")
    if result.source_articles:
        lines.append("근거 조문: " + ", ".join(result.source_articles))
    return "\n".join(lines)


async def run_calculation_for_query(query: str) -> CalcRun | None:
    """질문에서 계산 의도를 감지하면 계산기를 실행하고 결과를 반환한다.

    계산 대상이 아니거나 어느 단계든 실패하면 None (채팅은 RAG만으로 정상 진행).
    """
    if not has_calculation_intent(query):
        return None

    extracted = await extract_calculation_request(query)
    if not extracted:
        return None
    tool, params = extracted

    schema, calculator_module = _TOOLS[tool]
    try:
        req = schema(**params)
    except ValidationError as e:
        logger.warning("[CALC] 파라미터 검증 실패 tool=%s params=%s: %s", tool, params, e)
        return None

    resolved_params = req.model_dump()
    try:
        result = await calculator_module.calculate(**resolved_params)
    except Exception as e:
        logger.warning("[CALC] 계산 실행 실패 tool=%s: %s", tool, e)
        return None

    logger.info("[CALC] %s 계산 완료 — 결정세액 %d원", result.tax_type, result.final_tax)
    return CalcRun(
        context=format_calculation_context(result),
        tool=tool,
        params=resolved_params,
    )

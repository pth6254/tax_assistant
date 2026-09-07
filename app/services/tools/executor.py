"""한 질문당 도구 하나, 시간 제한, 인증 컨텍스트 주입."""
import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID
from pydantic import ValidationError
from app.services.calculator.errors import classify_error

from app.services.calculator.engine import CALCULATORS, CalcRun, run_calculation
from app.services.tools import document_search, law_lookup
from app.services.tools.registry import validate_arguments

logger = logging.getLogger(__name__)
TOOL_TIMEOUT_SEC = 30


@dataclass
class ToolRun:
    tool: str
    status: str
    context: str
    calculation: CalcRun | None = None
    error_code: str | None = None
    retryable: bool = False


async def execute_tool(tool: str, params: dict, *, user_id: str) -> ToolRun:
    try:
        UUID(user_id)  # 서버가 전달한 인증 컨텍스트만 사용한다.
        request = validate_arguments(tool, params)
        async with asyncio.timeout(TOOL_TIMEOUT_SEC):
            if tool in CALCULATORS:
                try:
                    calculation = await run_calculation(tool, request.model_dump())
                except Exception as exc:
                    raise classify_error(exc, operation=tool) from exc
                return ToolRun(tool, "ok", "", calculation)
            if tool == "law_lookup":
                status, context = await law_lookup.lookup(request)
            else:
                status, context = await document_search.search(request, user_id)
        if len(context) > 12000:
            context = context[:12000] + "\n[길이 제한으로 일부 생략됨. 전체 원문이라고 표현하지 마세요.]"
        return ToolRun(tool, status, context)
    except ValidationError as exc:
        missing = any(e["type"] == "missing" for e in exc.errors())
        return ToolRun(tool, "needs_input" if missing else "invalid_arguments",
                       "필수 입력이 부족합니다. 계산 조건을 추가해 주세요." if missing else "입력값의 형식과 범위를 확인해 주세요.",
                       error_code="missing_input" if missing else "invalid_input")
    except (ValueError, KeyError):
        return ToolRun(tool, "invalid_arguments", "도구 입력을 확인할 수 없습니다. 필요한 조건을 사용자에게 확인하세요.")
    except TimeoutError:
        return ToolRun(tool, "timeout", "도구 조회 시간이 초과됐습니다. 조회·계산 결과를 추측하지 마세요.", error_code="timeout", retryable=True)
    except Exception as exc:
        if tool in CALCULATORS:
            error = classify_error(exc, operation=tool)
            return ToolRun(tool, "error", error.message, error_code=error.code, retryable=error.retryable)
        logger.warning("Tool failed: %s (%s)", tool, type(exc).__name__)
        return ToolRun(tool, "error", "도구 실행에 실패했습니다. 조회·계산 결과를 추측하지 마세요.")

"""Public calculation failures: no raw database errors or guessed amounts."""
import logging
from asyncpg import PostgresConnectionError, CannotConnectNowError

logger = logging.getLogger(__name__)
_ERRORS = {
    "missing_tax_data": (503, False, "필요한 세율·공제 데이터가 없어 계산을 중단했습니다. 관리자에게 데이터 확인을 요청해 주세요."),
    "database_unavailable": (503, True, "계산 데이터베이스에 연결하지 못했습니다. 잠시 후 다시 계산해 주세요."),
    "timeout": (504, True, "계산 대기 시간이 초과되었습니다. 잠시 후 다시 계산해 주세요."),
    "unsupported_condition": (422, False, "현재 계산기가 지원하지 않는 조건입니다. 지원되는 조건을 선택하거나 세무 전문가에게 확인해 주세요."),
    "internal_error": (500, False, "계산 중 오류가 발생했습니다. 관리자에게 오류 확인을 요청해 주세요."),
}


class CalculationError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.http_status, self.retryable, self.message = _ERRORS[code]
        super().__init__(self.message)

    def detail(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def classify_error(exc: Exception, *, operation: str) -> CalculationError:
    if isinstance(exc, CalculationError):
        error = exc
    elif isinstance(exc, TimeoutError):
        error = CalculationError("timeout")
    elif isinstance(exc, (OSError, PostgresConnectionError, CannotConnectNowError)):
        error = CalculationError("database_unavailable")
    else:
        error = CalculationError("internal_error")
    logger.warning("Calculation failure operation=%s code=%s exception=%s", operation, error.code, type(exc).__name__)
    return error


def require_value(row: dict | None, field: str):
    # Zero is a valid configured value, not a missing value.
    if row is None or row.get(field) is None:
        raise CalculationError("missing_tax_data")
    return row[field]

"""허용 목록 및 입력 스키마의 단일 등록점."""
from app.schemas.tool_call import DocumentSearchRequest, LawLookupRequest
from app.services.calculator.engine import CALCULATORS

TOOL_SCHEMAS = {name: schema for name, (schema, _) in CALCULATORS.items()}
TOOL_SCHEMAS.update(law_lookup=LawLookupRequest, document_search=DocumentSearchRequest)


def validate_arguments(tool: str, params: dict):
    return TOOL_SCHEMAS[tool].model_validate(params, strict=True, extra="forbid")

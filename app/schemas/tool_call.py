"""Provider 중립 도구 입력. 인증 정보는 모델이 지정할 수 없다."""
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.ai_output import AIOutput, NonEmptyText
from app.services.law.reference_parser import parse_law_reference


class ToolSelection(AIOutput):
    tool: Literal["none", "income_tax", "capital_gains", "inheritance", "gift", "vat", "penalty_tax", "law_lookup", "document_search"]
    params: dict = Field(default_factory=dict)


class LawLookupRequest(AIOutput):
    law_name: NonEmptyText = Field(max_length=100)
    article_no: NonEmptyText = Field(max_length=100, description="제59조의4 제9항 제2호 가목처럼 가지번호·항·호·목을 구분")

    @field_validator("article_no")
    @classmethod
    def validate_reference(cls, value):
        reference = parse_law_reference(value)
        if reference.article is None or reference.law_name:
            raise ValueError("법령명은 law_name에, 조문 참조는 article_no에 지정")
        return value


class DocumentSearchRequest(AIOutput):
    query: NonEmptyText = Field(max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)

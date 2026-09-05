"""Validated LLM outputs. These validate structure, not legal truth."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class AIOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class QueryClassification(AIOutput):
    law: NonEmptyText
    queries: list[SearchQuery] = Field(min_length=1, max_length=3)


class Citation(AIOutput):
    label: Literal["법률", "시행령", "시행규칙"]
    law_name: NonEmptyText = Field(max_length=30)
    article_no: str = Field(pattern=r"^제[0-9]{1,4}조(의[0-9]{1,3})?$")


class CitationList(AIOutput):
    citations: list[Citation]


class CalculationExtraction(AIOutput):
    tool: Literal["none", "income_tax", "capital_gains", "inheritance", "gift", "vat", "penalty_tax"]
    params: dict = Field(default_factory=dict)

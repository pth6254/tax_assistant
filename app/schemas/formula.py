"""Bounded arithmetic plans: data, never executable model code."""
from typing import Literal
from pydantic import Field
from app.schemas.reliability import Contract


class ResearchArticle(Contract):
    law_name: str = Field(min_length=1, max_length=80)
    article_no: str = Field(min_length=1, max_length=40)


class FormulaResearch(Contract):
    articles: list[ResearchArticle] = Field(max_length=12)
    queries: list[str] = Field(min_length=1, max_length=2)


class FormulaRule(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    evidence_id: str
    span_ids: list[str] = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=240)


class FormulaValue(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(pattern=r"^-?\d{1,18}(?:\.\d{1,12})?$")
    unit: Literal["KRW", "ratio", "count"]
    origin: Literal["user", "assumption", "law", "constant"]
    quote: str = Field(max_length=400)
    rule_id: str = Field(max_length=40)


class FormulaBand(Contract):
    upper: str | None = Field(description="구간 상한(원), 최종 무한 구간만 null")
    rate: str = Field(description="비율, 예: 0.06")


class FormulaTable(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    rule_id: str
    bands: list[FormulaBand] = Field(min_length=1, max_length=12)


class FormulaStep(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=100)
    op: Literal["add", "subtract", "multiply", "divide", "min", "max", "progressive", "round"]
    args: list[str] = Field(min_length=1, max_length=12)
    table_id: str = Field(max_length=40)
    rule_ids: list[str] = Field(min_length=1, max_length=12)
    rounding: Literal["none", "floor_won", "truncate_won", "nearest_won"]


class FormulaOutput(Contract):
    label: str = Field(min_length=1, max_length=100)
    step_id: str
    role: Literal["component", "total", "prepaid", "balance"]


class FormulaPlan(Contract):
    title: str = Field(min_length=1, max_length=100)
    reference_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scope: str = Field(min_length=1, max_length=500)
    assumptions: list[str] = Field(max_length=12)
    follow_up: list[str] = Field(max_length=5)
    rules: list[FormulaRule] = Field(min_length=1, max_length=20)
    values: list[FormulaValue] = Field(min_length=1, max_length=45)
    tables: list[FormulaTable] = Field(max_length=4)
    steps: list[FormulaStep] = Field(min_length=1, max_length=60)
    outputs: list[FormulaOutput] = Field(min_length=1, max_length=8)


class FormulaReview(Contract):
    arithmetic_meaning_supported: bool
    user_facts_preserved: bool
    rules_complete: bool
    scope_and_assumptions_clear: bool
    issues: list[str] = Field(max_length=10)

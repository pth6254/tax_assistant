"""Inputs for the first supported consultation workflow: income tax."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictCaseModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CaseCreate(StrictCaseModel):
    title: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=5000)
    tax_year: int = Field(ge=2000, le=2100, strict=True)

    @model_validator(mode='after')
    def check_year_and_text(self):
        if self.tax_year > date.today().year or not self.title.strip() or not self.question.strip():
            raise ValueError('유효한 상담 제목·질문과 현재 연도 이전의 귀속연도를 입력하세요.')
        self.title = self.title.strip()
        self.question = self.question.strip()
        return self


class CaseFactsPatch(StrictCaseModel):
    income: int | None = Field(default=None, ge=0, strict=True)
    expense: int | None = Field(default=None, ge=0, strict=True)
    personal_deduction_count: int | None = Field(default=None, ge=1, strict=True)
    other_deductions: int | None = Field(default=None, ge=0, strict=True)


class CaseDocumentUpdate(StrictCaseModel):
    status: Literal['attached', 'not_available']
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def check_source(self):
        if self.status == 'attached' and not self.filename:
            raise ValueError('첨부 상태에는 문서 파일명이 필요합니다.')
        if self.status == 'not_available' and not (self.note or '').strip():
            raise ValueError('자료가 없는 이유를 입력하세요.')
        return self

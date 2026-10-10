"""Inputs for the first supported consultation workflow: income tax."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictCaseModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CaseCreate(StrictCaseModel):
    kind: Literal['income_tax', 'capital_gains', 'inheritance', 'gift', 'vat', 'penalty_tax'] = 'income_tax'
    title: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=5000)
    tax_year: int = Field(ge=2000, le=2100, strict=True)
    reference_date: date | None = None

    @model_validator(mode='after')
    def check_year_and_text(self):
        if self.tax_year > date.today().year or not self.title.strip() or not self.question.strip():
            raise ValueError('유효한 상담 제목·질문과 현재 연도 이전의 귀속연도를 입력하세요.')
        self.reference_date = self.reference_date or (date.today() if self.tax_year == date.today().year
                                                      else date(self.tax_year, 12, 31))
        if self.reference_date.year != self.tax_year or self.reference_date.year < 2000:
            raise ValueError('자료 조회 기준일과 기준연도를 일치시켜 주세요.')
        if self.reference_date > date.today():
            raise ValueError('미래 날짜의 자료 조회 기준일은 지원하지 않습니다.')
        self.title = self.title.strip()
        self.question = self.question.strip()
        return self


class CaseFactsPatch(StrictCaseModel):
    income: int | None = Field(default=None, ge=0, strict=True)
    expense: int | None = Field(default=None, ge=0, strict=True)
    personal_deduction_count: int | None = Field(default=None, ge=1, strict=True)
    other_deductions: int | None = Field(default=None, ge=0, strict=True)
    wage_income: int | None = Field(default=None, ge=0, strict=True)
    sincere_business: bool | None = None
    other_income: int | None = Field(default=None, ge=0, strict=True)
    interest_income: int | None = Field(default=None, ge=0, strict=True)
    dividend_gross_up: int | None = Field(default=None, ge=0, strict=True)
    withheld: bool | None = None
    itemized_special_credits: bool | None = None
    other_tax_credits: int | None = Field(default=None, ge=0, strict=True)
    prepaid_tax: int | None = Field(default=None, ge=0, strict=True)
    transfer_price: int | None = Field(default=None, ge=0, strict=True)
    acquisition_price: int | None = Field(default=None, ge=0, strict=True)
    expenses: int | None = Field(default=None, ge=0, strict=True)
    holding_years: int | None = Field(default=None, ge=0, strict=True)
    asset_type: Literal['주택', '토지·건물'] | None = None
    is_one_home: bool | None = None
    residence_years: int | None = Field(default=None, ge=0, strict=True)
    acquired_in_adjusted_area: bool | None = None
    multi_home_surcharge: Literal['없음', '2주택', '3주택이상'] | None = None
    estate_value: int | None = Field(default=None, ge=0, strict=True)
    debts: int | None = Field(default=None, ge=0, strict=True)
    spouse_inheritance: int | None = Field(default=None, ge=0, strict=True)
    children_count: int | None = Field(default=None, ge=0, strict=True)
    gift_amount: int | None = Field(default=None, ge=0, strict=True)
    relation: Literal['배우자', '직계존비속', '기타친족', '기타'] | None = None
    is_minor: bool | None = None
    prior_gifts_10y: int | None = Field(default=None, ge=0, strict=True)
    generation_skipping: bool | None = None
    marriage_birth: bool | None = None
    prior_gift_taxable: int | None = Field(default=None, ge=0, strict=True)
    prior_gift_tax: int | None = Field(default=None, ge=0, strict=True)
    deduction_used_10y: int | None = Field(default=None, ge=0, strict=True)
    filed_on_time: bool | None = None
    sales: int | None = Field(default=None, ge=0, strict=True)
    purchases: int | None = Field(default=None, ge=0, strict=True)
    exempt_sales: int | None = Field(default=None, ge=0, strict=True)
    is_simplified: bool | None = None
    business_type: Literal['소매업', '음식점업', '제조업', '숙박업', '건설업', '서비스업', '부동산임대업'] | None = None
    unpaid_tax: int | None = Field(default=None, ge=0, strict=True)
    penalty_type: Literal['무신고', '과소신고', '납부지연'] | None = None
    is_negligent: bool | None = None
    days_late: int | None = Field(default=None, ge=0, strict=True)


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

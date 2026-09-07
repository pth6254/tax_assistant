from typing import Annotated
from pydantic import BaseModel, Field

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]


# ── 응답 스키마 ──────────────────────────────────────────────────────

class TaxStep(BaseModel):
    label: str
    amount: int


class CalculationResult(BaseModel):
    tax_type: str
    steps: list[TaxStep]
    taxable_income: int
    calculated_tax: int
    final_tax: int
    effective_rate: float
    source_articles: list[str]


# ── 요청 스키마 ──────────────────────────────────────────────────────

class IncomeTaxRequest(BaseModel):
    income: NonNegativeInt
    expense: NonNegativeInt = 0
    personal_deduction_count: NonNegativeInt = 1
    other_deductions: NonNegativeInt = 0


class CapitalGainsRequest(BaseModel):
    transfer_price: NonNegativeInt
    acquisition_price: NonNegativeInt
    expenses: NonNegativeInt = 0
    holding_years: NonNegativeInt = 0
    asset_type: str = "부동산"
    is_one_home: bool = False


class InheritanceRequest(BaseModel):
    estate_value: NonNegativeInt
    debts: NonNegativeInt = 0
    spouse_inheritance: NonNegativeInt = 0
    children_count: NonNegativeInt = 0


class GiftTaxRequest(BaseModel):
    gift_amount: NonNegativeInt
    relation: str = "기타"
    is_minor: bool = False
    prior_gifts_10y: NonNegativeInt = 0


class VatRequest(BaseModel):
    sales: NonNegativeInt
    purchases: NonNegativeInt = 0
    exempt_sales: NonNegativeInt = 0
    is_simplified: bool = False
    business_type: str = "소매업"


class PenaltyTaxRequest(BaseModel):
    unpaid_tax: NonNegativeInt
    penalty_type: str = "무신고"       # 무신고 | 과소신고 | 납부지연
    is_negligent: bool = False        # 부정행위(사기·기타 부정한 방법) 여부 — 무신고/과소신고에만 적용
    days_late: NonNegativeInt = 0                # 납부지연에만 적용

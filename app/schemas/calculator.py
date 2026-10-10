from typing import Annotated, Literal
from pydantic import BaseModel, Field

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]


# ── 응답 스키마 ──────────────────────────────────────────────────────

class TaxStep(BaseModel):
    label: str
    amount: int


class TaxBasis(BaseModel):
    queried_on: str
    effective_dates: list[str]


class CalculationResult(BaseModel):
    tax_type: str
    steps: list[TaxStep]
    taxable_income: int
    calculated_tax: int
    final_tax: int
    effective_rate: float
    source_articles: list[str]
    basis: TaxBasis | None = None
    # Scope and assumptions a reader must see next to the amounts.
    notes: list[str] = Field(default_factory=list)


# ── 요청 스키마 ──────────────────────────────────────────────────────

class IncomeTaxRequest(BaseModel):
    income: NonNegativeInt
    expense: NonNegativeInt = 0
    personal_deduction_count: NonNegativeInt = 1
    other_deductions: NonNegativeInt = 0


class FinancialIncomeTaxRequest(BaseModel):
    """금융소득 종합과세를 포함한 종합소득세. 금액은 연간 총수입금액(원)."""
    interest_income: NonNegativeInt = Field(0, description="원천징수세율 14%가 적용되는 이자소득(예금·채권 이자 등)")
    non_business_interest: NonNegativeInt = Field(0, description="비영업대금의 이익(원천징수세율 25%)")
    dividend_gross_up: NonNegativeInt = Field(0, description="배당가산(Gross-up) 대상 배당소득(내국법인 배당 등)")
    dividend_other: NonNegativeInt = Field(0, description="배당가산 대상이 아닌 배당소득")
    other_income: NonNegativeInt = Field(0, description="금융소득 외 다른 종합소득금액(사업·근로 등 소득금액)")
    income_deductions: NonNegativeInt = Field(0, description="종합소득공제 합계액")
    withheld: bool = Field(True, description="금융소득이 국내에서 원천징수되었는지")


class CapitalGainsRequest(BaseModel):
    """국내 등기 부동산 1건의 양도. 기간은 만 연수(1년 6개월이면 1)."""
    transfer_price: NonNegativeInt = Field(description="양도가액(실지거래가액)")
    acquisition_price: NonNegativeInt = Field(description="취득가액(실지거래가액)")
    expenses: NonNegativeInt = Field(0, description="필요경비(취득세·중개수수료·자본적지출 등)")
    holding_years: NonNegativeInt = Field(0, description="보유기간(만 연수)")
    asset_type: Literal["주택", "토지·건물"] = "주택"
    is_one_home: bool = Field(False, description="양도일 현재 1세대 1주택인지")
    residence_years: NonNegativeInt = Field(0, description="보유기간 중 거주기간(만 연수)")
    acquired_in_adjusted_area: bool = Field(False, description="취득 당시 조정대상지역 주택인지")
    multi_home_surcharge: Literal["없음", "2주택", "3주택이상"] = Field(
        "없음", description="조정대상지역 다주택 중과 대상 구분(제104조 제7항)")


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

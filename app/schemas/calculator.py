from pydantic import BaseModel


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
    income: int
    expense: int = 0
    personal_deduction_count: int = 1
    other_deductions: int = 0


class CapitalGainsRequest(BaseModel):
    transfer_price: int
    acquisition_price: int
    expenses: int = 0
    holding_years: int = 0
    asset_type: str = "부동산"
    is_one_home: bool = False


class InheritanceRequest(BaseModel):
    estate_value: int
    debts: int = 0
    spouse_inheritance: int = 0
    children_count: int = 0


class GiftTaxRequest(BaseModel):
    gift_amount: int
    relation: str = "기타"
    is_minor: bool = False
    prior_gifts_10y: int = 0

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
    """종합소득세(금융소득 종합과세 포함). 금액은 연간 원 단위이고, 없는 소득은 0."""
    income: NonNegativeInt = Field(0, description="사업소득 총수입금액")
    expense: NonNegativeInt = Field(0, description="사업소득 필요경비")
    wage_income: NonNegativeInt = Field(0, description="근로소득 총급여액(비과세소득 제외, 근무지가 둘 이상이면 합계)")
    other_income: NonNegativeInt = Field(0, description="연금·기타소득 등 그 밖의 종합소득금액(필요경비·공제 차감 후)")
    interest_income: NonNegativeInt = Field(0, description="원천징수세율 14%가 적용되는 이자소득(예금·채권 이자 등)")
    non_business_interest: NonNegativeInt = Field(0, description="비영업대금의 이익(원천징수세율 25%)")
    dividend_gross_up: NonNegativeInt = Field(0, description="배당가산(Gross-up) 대상 배당소득(내국법인 배당 등)")
    dividend_other: NonNegativeInt = Field(0, description="배당가산 대상이 아닌 배당소득")
    withheld: bool = Field(True, description="금융소득이 국내에서 원천징수되었는지")
    personal_deduction_count: NonNegativeInt = Field(1, description="기본공제 인원(본인 포함)")
    other_deductions: NonNegativeInt = Field(0, description="기본공제 외 종합소득공제 합계(추가공제·연금보험료·특별소득공제 등)")
    itemized_special_credits: bool = Field(
        False, description="특별소득공제·특별세액공제·월세세액공제를 신청했는지(신청하면 표준세액공제 없음)")
    sincere_business: bool = Field(False, description="성실사업자(근로소득이 없을 때 표준세액공제 12만원)")
    other_tax_credits: NonNegativeInt = Field(
        0, description="근로소득·배당·표준세액공제 외 세액공제 합계(자녀·연금계좌·보험료·의료비·교육비·기부금 등)")
    prepaid_tax: NonNegativeInt = Field(0, description="중간예납·원천징수 등 기납부세액(금융소득 원천징수 제외)")


class FinancialIncomeTaxRequest(BaseModel):
    """이전 금융소득 계산기 입력(종합소득세 계산기의 별칭). 금액은 연간 총수입금액(원)."""
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
    """증여 1건의 증여세. 증여자 기준으로 관계를 고르고, 금액은 원 단위."""
    gift_amount: NonNegativeInt = Field(description="증여재산가액(시가 등 평가액)")
    relation: Literal["배우자", "직계존비속", "기타친족", "기타"] = Field(
        "기타", description="증여자와의 관계(직계존비속: 부모·조부모↔자녀·손자녀)")
    is_minor: bool = Field(False, description="수증자가 미성년자인지(직계존속에게 받으면 공제 2천만원)")
    prior_gifts_10y: NonNegativeInt = Field(
        0, description="같은 증여자(직계존속이면 그 배우자 포함)에게서 10년 내 받아 합산할 증여재산가액")
    debts: NonNegativeInt = Field(0, description="수증자가 인수한 증여재산 담보 채무(부담부증여)")
    prior_gift_tax: NonNegativeInt = Field(0, description="합산한 이전 증여의 산출세액(0이면 현행 기준으로 추정)")
    prior_gift_taxable: NonNegativeInt = Field(0, description="합산한 이전 증여의 과세표준(0이면 현행 기준으로 추정)")
    deduction_used_10y: NonNegativeInt = Field(
        0, description="합산하지 않은 다른 증여에 10년 내 이미 쓴 같은 관계의 증여재산공제")
    marriage_birth: bool = Field(False, description="직계존속에게 혼인신고일 전후 2년·자녀 출생일부터 2년 이내 받은 증여인지")
    marriage_birth_used: NonNegativeInt = Field(0, description="이미 받은 혼인·출산 증여재산공제(합계 1억원 한도)")
    generation_skipping: bool = Field(False, description="부모가 살아 있는 손자녀 등 자녀가 아닌 직계비속에게 증여(할증)")
    filed_on_time: bool = Field(True, description="신고기한(증여일이 속하는 달 말일부터 3개월) 내 신고")


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

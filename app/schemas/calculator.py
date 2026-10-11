from typing import Annotated, Literal
from pydantic import BaseModel, Field

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
Percent = Annotated[float, Field(ge=0, le=100)]


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
    business_method: Literal["장부", "단순경비율", "기준경비율"] = Field(
        "장부", description="사업소득금액 계산(장부: 수입-필요경비, 추계: 국세청 고시 경비율)")
    simple_rate: Percent = Field(0, description="업종 단순경비율(%, 기준경비율 방식의 비교소득금액에도 사용)")
    simple_excess_rate: Percent | None = Field(None, description="수입금액 4천만원 초과분 단순경비율(초과율, %)")
    standard_rate: Percent = Field(0, description="업종 기준경비율(%)")
    major_expenses: NonNegativeInt = Field(0, description="주요경비(매입비용·임차료·인건비, 증빙 금액)")
    double_entry: bool = Field(False, description="복식부기의무자(기준경비율 1/2, 배율 3.4)")
    pension_income: NonNegativeInt = Field(0, description="국민연금 등 공적연금 총연금액")
    private_pension: NonNegativeInt = Field(0, description="연금저축·IRP 등 사적연금 연금수령액")
    pension_age: NonNegativeInt = Field(0, description="사적연금 수령자 나이(원천징수율 5·4·3%)")
    misc_income: NonNegativeInt = Field(0, description="기타소득 총수입금액(강연료·원고료 등)")
    misc_expense_rule: Literal["실제", "60%", "80%"] = Field(
        "실제", description="기타소득 필요경비 의제(강연료·원고료 60%, 공익법인 상금 등 80%)")
    misc_expenses: NonNegativeInt = Field(0, description="기타소득 실제 필요경비")
    rental_income: NonNegativeInt = Field(0, description="주택임대 총수입금액(2천만원 이하면 분리과세와 비교)")
    rental_expenses: NonNegativeInt = Field(0, description="주택임대 실제 필요경비(종합과세 쪽 계산)")
    registered_rental: bool = Field(False, description="등록임대주택(분리과세 필요경비 60%, 공제 400만원)")
    daily_wage: NonNegativeInt = Field(0, description="일용근로 일급(분리과세로 끝남)")
    daily_work_days: NonNegativeInt = Field(0, description="일용근로 일수")


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
    """거주자 사망에 따른 상속 전체의 상속세. 금액은 원 단위."""
    estate_value: NonNegativeInt = Field(description="상속재산가액(보험금·퇴직금 등 간주상속재산, 추정상속재산 포함)")
    debts: NonNegativeInt = Field(0, description="상속인이 승계한 채무와 공과금 합계")
    spouse_inheritance: NonNegativeInt = Field(0, description="배우자가 실제 상속받은 금액(배우자가 승계한 채무 차감)")
    children_count: NonNegativeInt = Field(0, description="자녀 수(태아 포함)")
    funeral_expenses: NonNegativeInt = Field(0, description="장례비용(500만원 미만이면 500만원, 한도 1천만원)")
    memorial_expenses: NonNegativeInt = Field(0, description="봉안시설·자연장지 비용(한도 500만원)")
    financial_assets: NonNegativeInt = Field(0, description="순금융재산(예금·보험금·주식 등 금융재산 - 금융채무)")
    prior_gifts: NonNegativeInt = Field(0, description="상속인이 상속개시 전 10년 내 피상속인에게 받은 증여재산가액")
    prior_gifts_non_heirs: NonNegativeInt = Field(0, description="상속인 아닌 자가 상속개시 전 5년 내 받은 증여재산가액")
    prior_gifts_taxable: NonNegativeInt = Field(0, description="가산한 사전증여재산의 증여세 과세표준 합계")
    prior_gift_tax: NonNegativeInt = Field(0, description="가산한 사전증여재산의 증여세 산출세액 합계")
    has_spouse: bool = Field(False, description="배우자가 상속인인지(실제 상속받지 않아도 최소 5억원 공제)")
    spouse_prior_gifts_taxable: NonNegativeInt = Field(0, description="가산한 증여 중 배우자가 받은 증여의 과세표준")
    parents_count: NonNegativeInt = Field(0, description="자녀가 없을 때 상속인인 직계존속 수(배우자 법정상속분 계산)")
    minor_years: NonNegativeInt = Field(0, description="상속인·동거가족 중 미성년자의 19세까지 남은 연수 합계")
    elderly_count: NonNegativeInt = Field(0, description="상속인(배우자 제외)·동거가족 중 65세 이상인 사람 수")
    disabled_years: NonNegativeInt = Field(0, description="상속인·동거가족 중 장애인의 기대여명 연수 합계")
    non_heir_bequests: NonNegativeInt = Field(
        0, description="상속인 아닌 자에게 유증·사인증여한 재산과 상속포기로 다음 순위 상속인이 받은 재산")
    skipped_generation_assets: NonNegativeInt = Field(0, description="자녀가 아닌 직계비속(손자녀 등)이 받은 상속재산")
    skipped_generation_minor: bool = Field(False, description="그 손자녀 등이 미성년자인지(20억원 초과 시 40%)")
    filed_on_time: bool = Field(True, description="신고기한(상속개시일이 속하는 달 말일부터 6개월) 내 신고")


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
    """과세기간 1회 신고분 부가가치세. 일반과세자는 공급가액, 간이과세자는 공급대가(부가가치세 포함)로 입력."""
    sales: NonNegativeInt = Field(description="총매출(과세·영세율·면세 포함). 간이과세자는 공급대가")
    purchases: NonNegativeInt = Field(
        0, description="세금계산서·사업용 신용카드 등으로 받은 매입(일반: 공급가액, 간이: 공급대가)")
    exempt_sales: NonNegativeInt = Field(0, description="면세 공급가액(공통매입 안분 기준)")
    is_simplified: bool = Field(False, description="간이과세자인지")
    business_type: Literal["소매업", "음식점업", "제조업", "농업·임업·어업", "숙박업", "건설업", "운수·창고업",
                           "정보통신업", "부동산임대업", "서비스업"] = Field(
        "소매업", description="간이과세자 업종(부가가치율 15~40%)")
    zero_rated_sales: NonNegativeInt = Field(0, description="영세율 공급가액(수출 등)")
    common_purchases: NonNegativeInt = Field(0, description="과세·면세 공통매입 공급가액(면세비율만큼 불공제)")
    non_deductible_purchases: NonNegativeInt = Field(
        0, description="매입 중 공제받지 못하는 금액(비영업용 승용차·면세사업 관련 등)")
    deemed_purchases: NonNegativeInt = Field(0, description="음식점 개인사업자의 면세농산물 매입가액(의제매입세액)")
    card_sales: NonNegativeInt = Field(0, description="신용카드·현금영수증 발행 매출(공급대가)")
    card_credit_eligible: bool = Field(
        True, description="신용카드 발행세액공제 대상(법인·직전연도 공급가액 10억원 초과 개인은 아님)")
    card_credit_used: NonNegativeInt = Field(0, description="같은 해 이전 신고에서 받은 신용카드 발행세액공제")
    e_filing: bool = Field(False, description="확정신고를 전자신고하는 개인사업자(전자신고세액공제 1만원)")
    prepaid_tax: NonNegativeInt = Field(0, description="예정고지(부과)세액·예정신고 미환급세액")


class RetirementTaxRequest(BaseModel):
    """퇴직소득세(2020년 이후 퇴직). 근속연수는 1년 미만을 1년으로 올린 정산근속연수."""
    retirement_pay: NonNegativeInt = Field(description="과세대상 퇴직급여(퇴직금·퇴직연금 일시금, 비과세 제외)")
    service_years: Annotated[int, Field(ge=1, strict=True)] = Field(description="정산근속연수(1년 미만은 1년)")
    prepaid_tax: NonNegativeInt = Field(0, description="이미 원천징수된 퇴직소득세")


class PenaltyTaxRequest(BaseModel):
    """국세 신고·납부 가산세. 무신고·과소신고는 신고 가산세와 납부지연가산세를 함께 계산한다."""
    unpaid_tax: NonNegativeInt = Field(description="신고하지 않았거나 덜 신고·납부한 세액")
    penalty_type: Literal["무신고", "과소신고", "납부지연"] = Field(
        "무신고", description="무신고 | 과소신고 | 납부지연(기한 내 신고했지만 덜 냄)")
    is_negligent: bool = Field(False, description="부정행위(사기·그 밖의 부정한 행위)로 인한 무신고·과소신고인지")
    days_late: NonNegativeInt = Field(0, description="법정납부기한 다음 날부터 납부일(또는 고지일)까지 일수")
    filed_within_months: NonNegativeInt = Field(
        0, description="법정신고기한이 지난 뒤 기한 후 신고·수정신고한 개월 수(0이면 스스로 신고하지 않음)")
    revenue: NonNegativeInt = Field(0, description="복식부기의무자·법인의 수입금액(입력하면 수입금액 기준 하한 적용)")

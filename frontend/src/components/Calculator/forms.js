import { calcIncomeTax, calcCapitalGains, calcInheritance, calcGiftTax, calcVat, calcPenaltyTax, calcRetirement, calcVirtualAsset } from '../../api/calculatorApi.js'

// 챗봇 계산기 엔진(app/services/calculator/engine.py _TOOLS)의 도구명 → 화면 탭 키
const TOOL_TO_TAB = {
  income_tax:    'income',
  financial_income_tax: 'income',   // 이전 금융소득 계산기: 종합소득세 탭으로 연다
  capital_gains: 'capital',
  inheritance:   'inheritance',
  gift:          'gift',
  vat:           'vat',
  penalty_tax:   'penalty',
  retirement:    'retirement',
  virtual_asset: 'virtual',
}

const TABS = [
  { key: 'income',      label: '종합소득세', icon: '💼' },
  { key: 'capital',     label: '양도소득세', icon: '🏠' },
  { key: 'inheritance', label: '상속세',    icon: '📜' },
  { key: 'gift',        label: '증여세',    icon: '🎁' },
  { key: 'vat',         label: '부가가치세', icon: '🧾' },
  { key: 'retirement',  label: '퇴직소득세', icon: '🧳' },
  { key: 'virtual',     label: '가상자산',   icon: '🪙' },
  { key: 'penalty',     label: '가산세',    icon: '⏰' },
]

const FORMS = {
  income: {
    apiFn: calcIncomeTax,
    fields: [
      { key: 'wage_income',           label: '근로소득 총급여액',     unit: '만원', required: false, hint: '비과세 제외 · 근무지가 둘 이상이면 합계' },
      { key: 'business_method',       label: '사업소득 계산 방법',     type: 'select', options: ['장부', '단순경비율', '기준경비율'], hint: '장부가 없으면 국세청 고시 경비율로 추계' },
      { key: 'income',                label: '사업소득 총수입금액',   unit: '만원', required: false },
      { key: 'expense',               label: '사업소득 필요경비',     unit: '만원', required: false, hint: '장부 기준' },
      { key: 'simple_rate',           label: '단순경비율',            unit: '%',   required: false, hint: '홈택스 기준·단순경비율 조회' },
      { key: 'simple_excess_rate',    label: '단순경비율 초과율',      unit: '%',   required: false, hint: '수입 4천만원 초과분(없으면 비움)' },
      { key: 'standard_rate',         label: '기준경비율',            unit: '%',   required: false },
      { key: 'major_expenses',        label: '주요경비',              unit: '만원', required: false, hint: '매입·임차료·인건비' },
      { key: 'double_entry',          label: '복식부기의무자',         type: 'checkbox', hint: '기준경비율 1/2, 배율 3.4' },
      { key: 'pension_income',        label: '공적연금 총연금액',      unit: '만원', required: false, hint: '국민연금·공무원연금 등' },
      { key: 'private_pension',       label: '사적연금 연금수령액',    unit: '만원', required: false, hint: '연금저축·IRP · 분리과세와 비교' },
      { key: 'pension_age',           label: '사적연금 수령자 나이',   unit: '세',   required: false },
      { key: 'misc_income',           label: '기타소득 총수입금액',    unit: '만원', required: false, hint: '강연료·원고료 등' },
      { key: 'misc_expense_rule',     label: '기타소득 필요경비',      type: 'select', options: ['60%', '80%', '실제'] },
      { key: 'misc_expenses',         label: '기타소득 실제 필요경비', unit: '만원', required: false },
      { key: 'rental_income',         label: '주택임대 총수입금액',    unit: '만원', required: false, hint: '2천만원 이하면 분리과세와 비교' },
      { key: 'rental_expenses',       label: '주택임대 필요경비',      unit: '만원', required: false },
      { key: 'registered_rental',     label: '등록임대주택',          type: 'checkbox' },
      { key: 'daily_wage',            label: '일용근로 일급',          unit: '만원', required: false, hint: '분리과세로 끝남' },
      { key: 'daily_work_days',       label: '일용근로 일수',          unit: '일',   required: false },
      { key: 'other_income',          label: '그 밖의 종합소득금액',  unit: '만원', required: false, hint: '연금·기타소득 등 필요경비·공제를 뺀 소득금액' },
      { key: 'interest_income',       label: '이자소득',              unit: '만원', required: false, hint: '예금·채권 이자 등 원천징수세율 14%' },
      { key: 'non_business_interest', label: '비영업대금의 이익',     unit: '만원', required: false, hint: '개인 간 금전 대여 이자 등 원천징수세율 25%' },
      { key: 'dividend_gross_up',     label: '배당소득(배당가산 대상)', unit: '만원', required: false, hint: '내국법인 배당 등' },
      { key: 'dividend_other',        label: '배당소득(가산 대상 아님)', unit: '만원', required: false },
      { key: 'withheld',              label: '이자·배당이 국내에서 원천징수됨', type: 'checkbox', hint: '국외 소득 등 원천징수되지 않았다면 해제' },
      { key: 'personal_deduction_count', label: '기본공제 인원',      unit: '명',   required: false, hint: '본인 포함 (기본 1명)' },
      { key: 'other_deductions',      label: '그 밖의 소득공제 합계', unit: '만원', required: false, hint: '추가공제·연금보험료·특별소득공제 등 · 세액공제와 구분' },
      { key: 'itemized_special_credits', label: '특별소득공제·특별세액공제 신청', type: 'checkbox', hint: '신청하면 표준세액공제를 받지 않음' },
      { key: 'sincere_business',      label: '성실사업자',            type: 'checkbox', hint: '근로소득이 없을 때 표준세액공제 12만원(아니면 7만원)' },
      { key: 'other_tax_credits',     label: '그 밖의 세액공제 합계', unit: '만원', required: false, hint: '자녀·연금계좌·보험료·의료비·교육비·기부금 등' },
      { key: 'prepaid_tax',           label: '기납부세액',            unit: '만원', required: false, hint: '근로소득 원천징수·중간예납 등 · 이자·배당 원천징수는 자동 추정' },
    ],
    defaults: { personal_deduction_count: '1', withheld: true, business_method: '장부', misc_expense_rule: '60%' },
    toPayload: (f) => ({
      income:                   toWon(f.income),
      expense:                  (f.business_method || '장부') === '장부' ? toWon(f.expense) : 0,
      business_method:          f.business_method || '장부',
      simple_rate:              Number(f.simple_rate || 0),
      simple_excess_rate:       f.simple_excess_rate === '' || f.simple_excess_rate == null ? null : Number(f.simple_excess_rate),
      standard_rate:            Number(f.standard_rate || 0),
      major_expenses:           toWon(f.major_expenses),
      double_entry:             !!f.double_entry,
      pension_income:           toWon(f.pension_income),
      private_pension:          toWon(f.private_pension),
      pension_age:              toInt(f.pension_age),
      misc_income:              toWon(f.misc_income),
      misc_expense_rule:        f.misc_expense_rule || '60%',
      misc_expenses:            toWon(f.misc_expenses),
      rental_income:            toWon(f.rental_income),
      rental_expenses:          toWon(f.rental_expenses),
      registered_rental:        !!f.registered_rental,
      daily_wage:               toWon(f.daily_wage),
      daily_work_days:          toInt(f.daily_work_days),
      wage_income:              toWon(f.wage_income),
      other_income:             toWon(f.other_income),
      interest_income:          toWon(f.interest_income),
      non_business_interest:    toWon(f.non_business_interest),
      dividend_gross_up:        toWon(f.dividend_gross_up),
      dividend_other:           toWon(f.dividend_other),
      withheld:                 f.withheld !== false,
      personal_deduction_count: toInt(f.personal_deduction_count, 1),
      other_deductions:         toWon(f.other_deductions),
      itemized_special_credits: !!f.itemized_special_credits,
      sincere_business:         !!f.sincere_business,
      other_tax_credits:        toWon(f.other_tax_credits),
      prepaid_tax:              toWon(f.prepaid_tax),
    }),
  },
  capital: {
    apiFn: calcCapitalGains,
    fields: [
      { key: 'transfer_price',    label: '양도가액',    unit: '만원', required: true },
      { key: 'acquisition_price', label: '취득가액',    unit: '만원', required: true },
      { key: 'expenses',          label: '필요경비',    unit: '만원', required: false, hint: '취득세·중개수수료 등' },
      { key: 'holding_years',     label: '보유기간',    unit: '년',   required: false, hint: '만 연수(1년 6개월이면 1)' },
      { key: 'asset_type',        label: '자산유형',    type: 'select', options: ['주택', '토지·건물', '분양권', '조합원입주권', '기타자산', '주식', '파생상품', '신탁수익권'], hint: '기타자산: 회원권·영업권 등' },
      { key: 'non_business_land', label: '비사업용 토지', type: 'checkbox', hint: '기본세율 + 10%p' },
      { key: 'unregistered',      label: '미등기 양도',   type: 'checkbox', hint: '70%, 공제 없음' },
      { key: 'pre_approval_gain', label: '관리처분인가 전 양도차익', unit: '만원', required: false, hint: '원조합원만 장기보유특별공제' },
      { key: 'pre_approval_years', label: '인가 전 보유기간', unit: '년', required: false },
      { key: 'stock_market',      label: '주식 구분',     type: 'select', options: ['국내상장', '국내비상장', '국외'] },
      { key: 'major_shareholder', label: '대주주',        type: 'checkbox', hint: '상장 1%·코스닥 2% 또는 50억원, 비상장 4% 또는 10억원 등' },
      { key: 'sme',               label: '중소기업 주식', type: 'checkbox' },
      { key: 'same_group_loss',   label: '같은 그룹 양도차손', unit: '만원', required: false, hint: '같은 해 다른 자산 손실(통산)' },
      { key: 'is_one_home',       label: '1세대 1주택', type: 'checkbox', hint: '양도일 현재 세대가 이 주택 하나만 보유' },
      { key: 'residence_years',   label: '거주기간',    unit: '년',   required: false, hint: '보유기간 중 거주한 만 연수' },
      { key: 'acquired_in_adjusted_area', label: '취득 당시 조정대상지역', type: 'checkbox', hint: '1주택 비과세에 2년 거주 요건이 붙음' },
      { key: 'multi_home_surcharge', label: '다주택 중과', type: 'select', options: ['없음', '2주택', '3주택이상'], hint: '조정대상지역 중과 대상일 때만 선택' },
    ],
    defaults: { asset_type: '주택', multi_home_surcharge: '없음', stock_market: '국내비상장' },
    toPayload: (f) => ({
      transfer_price:    toWon(f.transfer_price),
      non_business_land: f.asset_type === '토지·건물' && !!f.non_business_land,
      unregistered:      ['주택', '토지·건물', '분양권', '조합원입주권', '기타자산'].includes(f.asset_type || '주택') && !!f.unregistered,
      pre_approval_gain: f.asset_type === '조합원입주권' ? toWon(f.pre_approval_gain) : 0,
      pre_approval_years: f.asset_type === '조합원입주권' ? toInt(f.pre_approval_years) : 0,
      stock_market:      f.stock_market || '국내비상장',
      major_shareholder: f.asset_type === '주식' && !!f.major_shareholder,
      sme:               f.asset_type === '주식' && !!f.sme,
      same_group_loss:   toWon(f.same_group_loss),
      acquisition_price: toWon(f.acquisition_price),
      expenses:          toWon(f.expenses),
      holding_years:     toInt(f.holding_years),
      asset_type:        f.asset_type || '주택',
      is_one_home:       (f.asset_type || '주택') === '주택' && !!f.is_one_home,
      residence_years:   ['주택', '조합원입주권'].includes(f.asset_type || '주택') ? toInt(f.residence_years) : 0,
      acquired_in_adjusted_area: (f.asset_type || '주택') === '주택' && !!f.acquired_in_adjusted_area,
      multi_home_surcharge: (f.asset_type || '주택') === '주택' ? f.multi_home_surcharge || '없음' : '없음',
    }),
  },
  inheritance: {
    apiFn: calcInheritance,
    fields: [
      { key: 'estate_value',       label: '상속재산가액',          unit: '만원', required: true, hint: '보험금·퇴직금 등 간주상속재산 포함' },
      { key: 'financial_assets',   label: '순금융재산',            unit: '만원', required: false, hint: '예금·보험금·주식 - 금융채무 · 20% 공제(최대 2억)' },
      { key: 'debts',              label: '채무·공과금',           unit: '만원', required: false },
      { key: 'funeral_expenses',   label: '장례비용',              unit: '만원', required: false, hint: '최소 500만원, 한도 1천만원' },
      { key: 'memorial_expenses',  label: '봉안시설 비용',          unit: '만원', required: false, hint: '한도 500만원' },
      { key: 'has_spouse',         label: '배우자 상속인',          type: 'checkbox', hint: '실제 상속이 없어도 최소 5억원 공제' },
      { key: 'spouse_inheritance', label: '배우자 실제 상속액',      unit: '만원', required: false, hint: '법정상속분·30억원 한도' },
      { key: 'children_count',     label: '자녀 수',               unit: '명',   required: false, hint: '1명당 5천만원' },
      { key: 'parents_count',      label: '상속인인 부모 수',        unit: '명',   required: false, hint: '자녀가 없을 때 배우자 법정상속분 계산' },
      { key: 'minor_years',        label: '미성년자 19세까지 연수 합계', unit: '년', required: false, hint: '1년당 1천만원' },
      { key: 'elderly_count',      label: '65세 이상 인원',         unit: '명',   required: false, hint: '배우자 제외, 1명당 5천만원' },
      { key: 'disabled_years',     label: '장애인 기대여명 연수 합계', unit: '년', required: false, hint: '1년당 1천만원' },
      { key: 'prior_gifts',        label: '10년 내 상속인 사전증여',  unit: '만원', required: false },
      { key: 'prior_gifts_non_heirs', label: '5년 내 상속인 외 사전증여', unit: '만원', required: false },
      { key: 'prior_gifts_taxable', label: '사전증여 과세표준 합계',   unit: '만원', required: false, hint: '공제 한도·증여세액공제 계산' },
      { key: 'prior_gift_tax',     label: '사전증여 산출세액 합계',   unit: '만원', required: false, hint: '증여세액공제' },
      { key: 'spouse_prior_gifts_taxable', label: '배우자 사전증여 과세표준', unit: '만원', required: false, hint: '배우자공제 한도에서 차감' },
      { key: 'non_heir_bequests',  label: '상속인 외 유증·상속포기분', unit: '만원', required: false, hint: '공제 한도에서 차감' },
      { key: 'skipped_generation_assets', label: '손자녀 등 상속분',   unit: '만원', required: false, hint: '세대생략 30% 할증' },
      { key: 'skipped_generation_minor', label: '손자녀 미성년',       type: 'checkbox', hint: '20억원 초과 시 40%' },
      { key: 'filed_on_time',      label: '기한 내 신고',           type: 'checkbox', hint: '신고세액공제 3%' },
    ],
    defaults: { has_spouse: true, filed_on_time: true },
    toPayload: (f) => ({
      estate_value:          toWon(f.estate_value),
      debts:                 toWon(f.debts),
      spouse_inheritance:    f.has_spouse === false ? 0 : toWon(f.spouse_inheritance),
      children_count:        toInt(f.children_count),
      funeral_expenses:      toWon(f.funeral_expenses),
      memorial_expenses:     toWon(f.memorial_expenses),
      financial_assets:      toWon(f.financial_assets),
      prior_gifts:           toWon(f.prior_gifts),
      prior_gifts_non_heirs: toWon(f.prior_gifts_non_heirs),
      prior_gifts_taxable:   toWon(f.prior_gifts_taxable),
      prior_gift_tax:        toWon(f.prior_gift_tax),
      has_spouse:            f.has_spouse !== false,
      spouse_prior_gifts_taxable: toWon(f.spouse_prior_gifts_taxable),
      parents_count:         toInt(f.parents_count),
      minor_years:           toInt(f.minor_years),
      elderly_count:         toInt(f.elderly_count),
      disabled_years:        toInt(f.disabled_years),
      non_heir_bequests:     toWon(f.non_heir_bequests),
      skipped_generation_assets: toWon(f.skipped_generation_assets),
      skipped_generation_minor: !!f.skipped_generation_minor,
      filed_on_time:         f.filed_on_time !== false,
    }),
  },
  gift: {
    apiFn: calcGiftTax,
    fields: [
      { key: 'gift_amount',         label: '증여재산가액',        unit: '만원', required: true, hint: '시가 등 평가액' },
      { key: 'relation',            label: '증여자와의 관계',      type: 'select', options: ['직계존비속', '배우자', '기타친족', '기타'] },
      { key: 'is_minor',            label: '수증자 미성년자',      type: 'checkbox', hint: '직계존속에게 받으면 공제 2천만원' },
      { key: 'generation_skipping', label: '세대생략(조부모→손자녀)', type: 'checkbox', hint: '부모가 생존하면 30% 할증' },
      { key: 'marriage_birth',      label: '혼인·출산 공제 대상',    type: 'checkbox', hint: '혼인신고 전후 2년·출생 후 2년 이내, 2024년 이후 증여' },
      { key: 'debts',               label: '인수 채무(부담부증여)',  unit: '만원', required: false, hint: '전세·임대보증금, 담보대출' },
      { key: 'prior_gifts_10y',     label: '10년 내 동일인 증여액', unit: '만원', required: false, hint: '부모는 두 분을 한 사람으로 봄' },
      { key: 'prior_gift_taxable',  label: '이전 증여 과세표준',     unit: '만원', required: false, hint: '모르면 비워 두면 추정' },
      { key: 'prior_gift_tax',      label: '이전 증여 산출세액',     unit: '만원', required: false, hint: '모르면 비워 두면 추정' },
      { key: 'deduction_used_10y',  label: '이미 쓴 증여재산공제',   unit: '만원', required: false, hint: '합산하지 않은 다른 증여에 쓴 같은 관계 공제' },
      { key: 'filed_on_time',       label: '기한 내 신고',          type: 'checkbox', hint: '신고세액공제 3%' },
    ],
    defaults: { relation: '직계존비속', filed_on_time: true },
    toPayload: (f) => ({
      gift_amount:         toWon(f.gift_amount),
      relation:            f.relation || '직계존비속',
      is_minor:            f.relation === '직계존비속' && !!f.is_minor,
      prior_gifts_10y:     toWon(f.prior_gifts_10y),
      debts:               toWon(f.debts),
      prior_gift_tax:      toWon(f.prior_gift_tax),
      prior_gift_taxable:  toWon(f.prior_gift_taxable),
      deduction_used_10y:  toWon(f.deduction_used_10y),
      marriage_birth:      f.relation === '직계존비속' && !!f.marriage_birth,
      marriage_birth_used: 0,
      generation_skipping: f.relation === '직계존비속' && !!f.generation_skipping,
      filed_on_time:       f.filed_on_time !== false,
    }),
  },
  vat: {
    apiFn: calcVat,
    fields: [
      { key: 'is_simplified', label: '간이과세자',      type: 'checkbox' },
      { key: 'business_type', label: '업종',           type: 'select',
        options: ['소매업', '음식점업', '제조업', '농업·임업·어업', '숙박업', '건설업', '운수·창고업', '정보통신업', '부동산임대업', '서비스업'],
        hint: '간이과세자 부가가치율 15~40%' },
      { key: 'sales',         label: '총매출',          unit: '만원', required: true, hint: '일반: 공급가액(부가세 제외) · 간이: 공급대가(부가세 포함)' },
      { key: 'zero_rated_sales', label: '영세율 매출',   unit: '만원', required: false, hint: '수출 등' },
      { key: 'exempt_sales',  label: '면세 매출',        unit: '만원', required: false, hint: '공통매입 안분 기준' },
      { key: 'purchases',     label: '공제받는 매입',    unit: '만원', required: false, hint: '세금계산서·사업용 카드 매입' },
      { key: 'non_deductible_purchases', label: '그중 불공제 매입', unit: '만원', required: false, hint: '비영업용 승용차·접대비 등' },
      { key: 'common_purchases', label: '과세·면세 공통매입', unit: '만원', required: false, hint: '면세 매출 비율만큼 불공제' },
      { key: 'deemed_purchases', label: '면세농산물 매입',  unit: '만원', required: false, hint: '음식점 개인사업자 의제매입세액' },
      { key: 'card_sales',    label: '카드·현금영수증 매출', unit: '만원', required: false, hint: '발행세액공제 1.3%(연 1천만원)' },
      { key: 'card_credit_eligible', label: '카드 발행공제 대상', type: 'checkbox', hint: '법인·직전연도 공급가액 10억 초과 개인은 해제' },
      { key: 'card_credit_used', label: '올해 이미 받은 카드공제', unit: '만원', required: false },
      { key: 'prepaid_tax',   label: '예정고지·미환급세액', unit: '만원', required: false },
      { key: 'e_filing',      label: '전자신고(1만원 공제)', type: 'checkbox' },
    ],
    defaults: { business_type: '소매업', card_credit_eligible: true },
    toPayload: (f) => ({
      sales:         toWon(f.sales),
      purchases:     toWon(f.purchases),
      exempt_sales:  f.is_simplified ? 0 : toWon(f.exempt_sales),
      is_simplified: !!f.is_simplified,
      business_type: f.business_type || '소매업',
      zero_rated_sales: f.is_simplified ? 0 : toWon(f.zero_rated_sales),
      common_purchases: f.is_simplified ? 0 : toWon(f.common_purchases),
      non_deductible_purchases: f.is_simplified ? 0 : toWon(f.non_deductible_purchases),
      deemed_purchases: f.is_simplified ? 0 : toWon(f.deemed_purchases),
      card_sales:    toWon(f.card_sales),
      card_credit_eligible: f.card_credit_eligible !== false,
      card_credit_used: toWon(f.card_credit_used),
      e_filing:      !!f.e_filing,
      prepaid_tax:   toWon(f.prepaid_tax),
    }),
  },
  retirement: {
    apiFn: calcRetirement,
    fields: [
      { key: 'retirement_pay', label: '퇴직급여',     unit: '만원', required: true, hint: '퇴직금·퇴직연금 일시금(비과세 제외)' },
      { key: 'service_years',  label: '근속연수',     unit: '년',   required: true, hint: '1년 미만은 1년으로 올림 · 중간정산 시 중복기간 제외' },
      { key: 'prepaid_tax',    label: '원천징수된 세액', unit: '만원', required: false },
    ],
    defaults: {},
    toPayload: (f) => ({
      retirement_pay: toWon(f.retirement_pay),
      service_years:  toInt(f.service_years, 1),
      prepaid_tax:    toWon(f.prepaid_tax),
    }),
  },
  virtual: {
    apiFn: calcVirtualAsset,
    fields: [
      { key: 'transfer_price',    label: '양도가액',       unit: '만원', required: true, hint: '같은 해 전체(총평균법)' },
      { key: 'acquisition_price', label: '실제 취득가액',   unit: '만원', required: true },
      { key: 'expenses',          label: '수수료 등 경비', unit: '만원', required: false },
      { key: 'held_before_2027',  label: '2027년 전부터 보유', type: 'checkbox', hint: '2026-12-31 시가와 비교' },
      { key: 'value_2026_end',    label: '2026-12-31 시가', unit: '만원', required: false },
    ],
    defaults: {},
    toPayload: (f) => ({
      transfer_price:    toWon(f.transfer_price),
      acquisition_price: toWon(f.acquisition_price),
      expenses:          toWon(f.expenses),
      held_before_2027:  !!f.held_before_2027,
      value_2026_end:    f.held_before_2027 ? toWon(f.value_2026_end) : 0,
    }),
  },
  penalty: {
    apiFn: calcPenaltyTax,
    fields: [
      { key: 'unpaid_tax',    label: '무신고·과소신고·미납 세액', unit: '만원', required: true },
      { key: 'penalty_type',  label: '경우', type: 'select', options: ['무신고', '과소신고', '납부지연'], hint: '무신고·과소신고는 납부지연가산세도 함께 계산' },
      { key: 'is_negligent',  label: '부정행위(사기·기타 부정한 방법)', type: 'checkbox', hint: '무신고·과소신고만 해당' },
      { key: 'filed_within_months', label: '기한 후 신고·수정신고 시점', unit: '개월', required: false, hint: '법정신고기한 후 몇 개월 안에 스스로 신고(감면)' },
      { key: 'days_late',     label: '납부지연 일수', unit: '일', required: false, hint: '법정납부기한 다음 날부터 납부일까지' },
      { key: 'revenue',       label: '수입금액(복식부기의무자·법인)', unit: '만원', required: false, hint: '무신고 시 수입금액 1만분의 7 하한' },
    ],
    defaults: { penalty_type: '무신고' },
    toPayload: (f) => ({
      unpaid_tax:   toWon(f.unpaid_tax),
      penalty_type: f.penalty_type || '무신고',
      is_negligent: f.penalty_type !== '납부지연' && !!f.is_negligent,
      days_late:    toInt(f.days_late),
      filed_within_months: f.penalty_type === '납부지연' ? 0 : toInt(f.filed_within_months),
      revenue:      f.penalty_type === '납부지연' ? 0 : toWon(f.revenue),
    }),
  },
}

const toWon = v => Math.round(Number(v || 0) * 10_000)
const toInt = (v, def = 0) => v === '' || v == null ? def : Number(v)
const fromWon = v => String(Number(v || 0) / 10_000)
const fmtWon  = (v) => (v || 0).toLocaleString('ko-KR') + '원'

// 챗봇 계산기 엔진이 전달한 원(₩) 단위 params → 화면 폼(만원 단위) 값으로 역변환
const buildFormFromParams = (tabKey, params) => {
  const { fields, defaults } = FORMS[tabKey]
  // 이전 금융소득 계산기의 소득공제 합계(기본공제 포함)는 기본공제 0명 + 그 밖의 소득공제로 옮긴다.
  if (tabKey === 'income' && 'income_deductions' in params) {
    params = { ...params, personal_deduction_count: 0, other_deductions: params.income_deductions }
  }
  const form = { ...defaults }
  for (const field of fields) {
    if (!(field.key in params) || params[field.key] == null) continue
    const raw = params[field.key]
    if (field.type === 'checkbox') form[field.key] = !!raw
    else if (field.type === 'select') form[field.key] = raw
    else if (field.unit === '만원') form[field.key] = fromWon(raw)
    else form[field.key] = String(raw)
  }
  return form
}

// 계산 결과를 챗봇에 질문하기 위한 자연어 문장 구성
const QUESTION_BUILDERS = {
  income: (f, r) => {
    const parts = [['총급여', f.wage_income], ['사업 수입', f.income], ['사업 필요경비', f.expense], ['그 밖의 소득금액', f.other_income],
      ['공적연금', f.pension_income], ['사적연금', f.private_pension], ['기타소득', f.misc_income], ['주택임대 수입', f.rental_income],
      ['이자', f.interest_income], ['비영업대금 이익', f.non_business_interest],
      ['배당', Number(f.dividend_gross_up || 0) + Number(f.dividend_other || 0)]]
      .filter(([, v]) => Number(v || 0) > 0).map(([label, v]) => `${label} ${v}만원`)
    return `${parts.join(', ') || '소득 0원'}, 기본공제 ${f.personal_deduction_count || 1}명 기준으로 ` +
      `계산한 종합소득세 결정세액이 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`
  },
  capital: (f, r) =>
    `${f.asset_type || '주택'} 양도가액 ${f.transfer_price || 0}만원, 취득가액 ${f.acquisition_price || 0}만원, 보유기간 ${f.holding_years || 0}년` +
    `${f.is_one_home ? `, 1세대 1주택, 거주기간 ${f.residence_years || 0}년` : ''} 기준으로 ` +
    `계산한 양도소득세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`,
  inheritance: (f, r) =>
    `상속재산 ${f.estate_value || 0}만원, ${f.has_spouse === false ? '배우자 없음' : `배우자 실제 상속액 ${f.spouse_inheritance || 0}만원`}, 자녀 ${f.children_count || 0}명` +
    `${Number(f.prior_gifts || 0) > 0 ? `, 10년 내 사전증여 ${f.prior_gifts}만원` : ''} 기준으로 ` +
    `계산한 상속세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 공제받을 수 있는 항목이 있으면 알려주세요.`,
  gift: (f, r) =>
    `증여재산 ${f.gift_amount || 0}만원을 ${f.relation || '직계존비속'} 관계에서 증여받는 경우` +
    `${Number(f.debts || 0) > 0 ? `(인수 채무 ${f.debts}만원)` : ''}${Number(f.prior_gifts_10y || 0) > 0 ? `, 10년 내 동일인 증여 ${f.prior_gifts_10y}만원 합산` : ''}` +
    `${f.relation === '직계존비속' && f.generation_skipping ? ', 세대생략 할증' : ''}${f.relation === '직계존비속' && f.marriage_birth ? ', 혼인·출산 공제' : ''}로 ` +
    `계산한 증여세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`,
  vat: (f, r) =>
    `매출 ${f.sales || 0}만원, 매입 ${f.purchases || 0}만원${f.is_simplified ? ` (간이과세자, ${f.business_type} 업종)` : ' (일반과세자)'} 기준으로 ` +
    `계산한 부가가치세 ${r.final_tax < 0 ? '환급세액' : '납부세액'}이 ${fmtWon(Math.abs(r.final_tax))}로 나왔습니다. 이 계산이 맞는지 확인해주세요.`,
  retirement: (f, r) =>
    `퇴직급여 ${f.retirement_pay || 0}만원, 근속 ${f.service_years || 0}년 기준으로 계산한 퇴직소득세가 ${fmtWon(r.final_tax)}로 나왔습니다. ` +
    `이 계산이 맞는지 확인하고, 연금계좌로 받는 경우와 비교해 주세요.`,
  virtual: (f, r) =>
    `가상자산 양도가액 ${f.transfer_price || 0}만원, 취득가액 ${f.acquisition_price || 0}만원 기준으로 계산한 세금이 ${fmtWon(r.final_tax)}로 ` +
    `나왔습니다. 2027년 과세 시작 전후를 포함해 이 계산이 맞는지 확인해 주세요.`,
  penalty: (f, r) =>
    `${f.penalty_type || '무신고'} 세액 ${f.unpaid_tax || 0}만원${f.is_negligent && f.penalty_type !== '납부지연' ? ' (부정행위)' : ''}, 납부지연 ${f.days_late || 0}일` +
    `${Number(f.filed_within_months || 0) > 0 && f.penalty_type !== '납부지연' ? `, 기한 후 ${f.filed_within_months}개월 안에 스스로 신고` : ''} 기준으로 ` +
    `계산한 가산세 포함 납부할 총액이 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인해주세요.`,
}


export { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS }

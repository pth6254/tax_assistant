import { calcIncomeTax, calcCapitalGains, calcInheritance, calcGiftTax, calcVat, calcPenaltyTax } from '../../api/calculatorApi'

// 챗봇 계산기 엔진(app/services/calculator/engine.py _TOOLS)의 도구명 → 화면 탭 키
const TOOL_TO_TAB = {
  income_tax:    'income',
  capital_gains: 'capital',
  inheritance:   'inheritance',
  gift:          'gift',
  vat:           'vat',
  penalty_tax:   'penalty',
}

const TABS = [
  { key: 'income',      label: '소득세',    icon: '💼' },
  { key: 'capital',     label: '양도소득세', icon: '🏠' },
  { key: 'inheritance', label: '상속세',    icon: '📜' },
  { key: 'gift',        label: '증여세',    icon: '🎁' },
  { key: 'vat',         label: '부가가치세', icon: '🧾' },
  { key: 'penalty',     label: '가산세',    icon: '⏰' },
]

const FORMS = {
  income: {
    apiFn: calcIncomeTax,
    fields: [
      { key: 'income',                   label: '총소득금액',    unit: '만원', required: true,  hint: '현재 사업소득 중심의 단순 계산식' },
      { key: 'expense',                  label: '필요경비',      unit: '만원', required: false, hint: '사업자만 해당' },
      { key: 'personal_deduction_count', label: '기본공제 인원', unit: '명',   required: false, hint: '본인 포함 (기본 1명)' },
      { key: 'other_deductions',         label: '기타공제 합계', unit: '만원', required: false, hint: '과세표준에서 차감할 소득공제액 · 세액공제와 구분' },
    ],
    defaults: { personal_deduction_count: '1' },
    toPayload: (f) => ({
      income:                   toWon(f.income),
      expense:                  toWon(f.expense),
      personal_deduction_count: toInt(f.personal_deduction_count, 1),
      other_deductions:         toWon(f.other_deductions),
    }),
  },
  capital: {
    apiFn: calcCapitalGains,
    fields: [
      { key: 'transfer_price',    label: '양도가액',    unit: '만원', required: true },
      { key: 'acquisition_price', label: '취득가액',    unit: '만원', required: true },
      { key: 'expenses',          label: '필요경비',    unit: '만원', required: false, hint: '취득세·중개수수료 등' },
      { key: 'holding_years',     label: '보유기간',    unit: '년',   required: false },
      { key: 'asset_type',        label: '자산유형',    type: 'select', options: ['부동산'] },
      { key: 'is_one_home',       label: '1세대 1주택', type: 'checkbox', hint: '구현된 장기보유 공제 조건에만 반영 · 비과세 자동 판정 아님' },
    ],
    defaults: { asset_type: '부동산' },
    toPayload: (f) => ({
      transfer_price:    toWon(f.transfer_price),
      acquisition_price: toWon(f.acquisition_price),
      expenses:          toWon(f.expenses),
      holding_years:     toInt(f.holding_years),
      asset_type:        f.asset_type || '부동산',
      is_one_home:       !!f.is_one_home,
    }),
  },
  inheritance: {
    apiFn: calcInheritance,
    fields: [
      { key: 'estate_value',       label: '상속재산가액', unit: '만원', required: true },
      { key: 'debts',              label: '채무·공과금',  unit: '만원', required: false },
      { key: 'spouse_inheritance', label: '배우자 상속액', unit: '만원', required: false },
      { key: 'children_count',     label: '자녀 수',      unit: '명',   required: false },
    ],
    defaults: {},
    toPayload: (f) => ({
      estate_value:       toWon(f.estate_value),
      debts:              toWon(f.debts),
      spouse_inheritance: toWon(f.spouse_inheritance),
      children_count:     toInt(f.children_count),
    }),
  },
  gift: {
    apiFn: calcGiftTax,
    fields: [
      { key: 'gift_amount',     label: '증여재산가액',       unit: '만원', required: true },
      { key: 'relation',        label: '증여자와의 관계',     type: 'select', options: ['직계존비속', '배우자', '기타친족', '기타'] },
      { key: 'is_minor',        label: '수증자 미성년자',     type: 'checkbox' },
      { key: 'prior_gifts_10y', label: '10년 내 사전증여액', unit: '만원', required: false, hint: '동일인으로부터' },
    ],
    defaults: { relation: '기타' },
    toPayload: (f) => ({
      gift_amount:     toWon(f.gift_amount),
      relation:        f.relation || '기타',
      is_minor:        !!f.is_minor,
      prior_gifts_10y: toWon(f.prior_gifts_10y),
    }),
  },
  vat: {
    apiFn: calcVat,
    fields: [
      { key: 'sales',         label: '매출액',        unit: '만원', required: true },
      { key: 'purchases',     label: '매입액',        unit: '만원', required: false },
      { key: 'exempt_sales',  label: '영세율·면세 매출', unit: '만원', required: false, hint: '과세매출에서 제외' },
      { key: 'is_simplified', label: '간이과세자',      type: 'checkbox' },
      { key: 'business_type', label: '업종',           type: 'select',
        options: ['소매업', '음식점업', '제조업', '숙박업', '건설업', '서비스업', '부동산임대업'],
        hint: '간이과세자만 해당' },
    ],
    defaults: { business_type: '소매업' },
    toPayload: (f) => ({
      sales:         toWon(f.sales),
      purchases:     toWon(f.purchases),
      exempt_sales:  toWon(f.exempt_sales),
      is_simplified: !!f.is_simplified,
      business_type: f.business_type || '소매업',
    }),
  },
  penalty: {
    apiFn: calcPenaltyTax,
    fields: [
      { key: 'unpaid_tax',    label: '무신고·과소신고·미납 세액', unit: '만원', required: true },
      { key: 'penalty_type',  label: '가산세 종류', type: 'select', options: ['무신고', '과소신고', '납부지연'] },
      { key: 'is_negligent',  label: '부정행위(사기·기타 부정한 방법)', type: 'checkbox', hint: '무신고·과소신고만 해당' },
      { key: 'days_late',     label: '연체일수', unit: '일', required: false, hint: '납부지연만 해당' },
    ],
    defaults: { penalty_type: '무신고' },
    toPayload: (f) => ({
      unpaid_tax:   toWon(f.unpaid_tax),
      penalty_type: f.penalty_type || '무신고',
      is_negligent: !!f.is_negligent,
      days_late:    toInt(f.days_late),
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
  const form = { ...defaults }
  for (const field of fields) {
    if (!(field.key in params)) continue
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
  income: (f, r) =>
    `총수입 ${f.income || 0}만원, 필요경비 ${f.expense || 0}만원, 부양가족 ${f.personal_deduction_count || 1}명 기준으로 ` +
    `계산한 종합소득세 결정세액이 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`,
  capital: (f, r) =>
    `양도가액 ${f.transfer_price || 0}만원, 취득가액 ${f.acquisition_price || 0}만원, 보유기간 ${f.holding_years || 0}년 기준으로 ` +
    `계산한 양도소득세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`,
  inheritance: (f, r) =>
    `상속재산 ${f.estate_value || 0}만원, 배우자 상속액 ${f.spouse_inheritance || 0}만원, 자녀 ${f.children_count || 0}명 기준으로 ` +
    `계산한 상속세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 공제받을 수 있는 항목이 있으면 알려주세요.`,
  gift: (f, r) =>
    `증여재산 ${f.gift_amount || 0}만원을 ${f.relation || '기타'} 관계에서 증여받는 경우로 ` +
    `계산한 증여세가 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인하고, 추가로 절세 방법이 있으면 알려주세요.`,
  vat: (f, r) =>
    `매출 ${f.sales || 0}만원, 매입 ${f.purchases || 0}만원${f.is_simplified ? ` (간이과세자, ${f.business_type} 업종)` : ' (일반과세자)'} 기준으로 ` +
    `계산한 부가가치세 ${r.final_tax < 0 ? '환급세액' : '납부세액'}이 ${fmtWon(Math.abs(r.final_tax))}로 나왔습니다. 이 계산이 맞는지 확인해주세요.`,
  penalty: (f, r) =>
    `${f.penalty_type || '무신고'} 세액 ${f.unpaid_tax || 0}만원${f.penalty_type === '납부지연' ? ` (연체 ${f.days_late || 0}일)` : (f.is_negligent ? ' (부정행위)' : '')} 기준으로 ` +
    `계산한 가산세 포함 납부할 총액이 ${fmtWon(r.final_tax)}로 나왔습니다. 이 계산이 맞는지 확인해주세요.`,
}


export { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS }

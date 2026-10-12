import { useEffect, useRef, useState } from 'react'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from './forms'
import ResultCard from './ResultCard'
import Notice from '../ui/Notice'
import Icon from '../ui/Icon'
const CAPITAL_ASSETS = FORMS.capital.fields.find(f => f.key === 'asset_type').options

export default function CalculatorScreen({ initial, onInitialConsumed, onAskAboutResult }) {
  const [tab, setTab] = useState('income'), [form, setForm] = useState({ ...FORMS.income.defaults })
  const [result, setResult] = useState(null), [snapshot, setSnapshot] = useState(null), [loading, setLoading] = useState(false), [error, setError] = useState(null)
  const revision = useRef(0), firstInput = useRef(), formElement = useRef()
  const invalidate = () => { ++revision.current; setResult(null); setSnapshot(null); setError(null); setLoading(false) }
  useEffect(() => () => { ++revision.current }, [])
  useEffect(() => {
    if (!initial) return
    const key = TOOL_TO_TAB[initial.tool]
    if (key) {
      invalidate(); setTab(key); setForm(buildFormFromParams(key, initial.params || {}))
      if (key === 'capital' && initial.params?.asset_type && !CAPITAL_ASSETS.includes(initial.params.asset_type)) setError({ message: '현재 양도소득세는 주택·토지·건물만 지원합니다. 조건을 다시 확인하세요.' })
    }
    onInitialConsumed?.()
  }, [initial])
  const change = (key, value) => { invalidate(); setForm(previous => ({ ...previous, [key]: value })) }
  const submit = async e => {
    e.preventDefault()
    const version = ++revision.current
    setResult(null); setError(null)
    const { apiFn, fields, toPayload } = FORMS[tab]
    const missing = fields.filter(f => f.required && (form[f.key] === '' || form[f.key] == null))
    if (missing.length) { setError({ message: '필수 항목을 입력하세요: ' + missing.map(f => f.label).join(', ') }); firstInput.current?.focus(); return }
    if (!formElement.current.reportValidity()) return
    const payload = toPayload(form)
    if (Object.values(payload).some(v => typeof v === 'number' && (!Number.isSafeInteger(v) || v < 0))) {
      setError({ message: '금액은 원 단위로 환산 가능한 범위, 인원·기간은 0 이상의 정수로 입력해 주세요.' }); return
    }
    if (tab === 'capital' && !CAPITAL_ASSETS.includes(payload.asset_type)) { setError({ message: '현재 주택·토지·건물만 지원합니다.' }); return }
    setLoading(true)
    try {
      const data = await apiFn(payload)
      if (version === revision.current) { setResult(data); setSnapshot({ ...form }) }
    } catch (e) { if (version === revision.current) setError({ message: e.message, retryable: e.retryable }) }
    finally { if (version === revision.current) setLoading(false) }
  }
  const fields = FORMS[tab].fields
  const hasFinancial = ['interest_income', 'non_business_interest', 'dividend_gross_up', 'dividend_other'].some(k => Number(form[k] || 0) > 0)
  const penaltyType = form.penalty_type || '없음'
  const visible = fields.filter(f => !(f.key === 'business_type' && !form.is_simplified)
    && !(['reported_tax', 'is_negligent', 'filed_within_months', 'days_late', 'penalty_revenue'].includes(f.key) && penaltyType === '없음')
    && !(f.key === 'reported_tax' && penaltyType === '무신고')
    && !(['is_negligent', 'filed_within_months'].includes(f.key) && penaltyType === '납부지연')
    && !(f.key === 'penalty_revenue' && !(penaltyType === '무신고' || (penaltyType === '과소신고' && form.is_negligent)))
    && !(f.key === 'filed_on_time' && penaltyType === '무신고')
    && !(f.key === 'reported_taxable' && penaltyType !== '과소신고')
    && !(f.key === 'reported_zero_rated_sales' && (penaltyType !== '과소신고' || form.is_simplified))
    && !(f.key === 'rental_house_count' && !(Number(form.rental_deposits || 0) > 0))
    && !(f.key === 'religious_as_wage' && !(Number(form.religious_income || 0) > 0))
    && !(['prior_same_year_taxable', 'prior_same_year_tax'].includes(f.key) && ['주식', '파생상품', '신탁수익권'].includes(form.asset_type))
    && !(['zero_rated_sales', 'exempt_sales', 'non_deductible_purchases', 'common_purchases', 'deemed_purchases'].includes(f.key) && form.is_simplified)
    && !(f.key === 'withheld' && !hasFinancial)
    && !(['virtual_acquisition_price', 'virtual_expenses', 'virtual_held_before_2027'].includes(f.key) && !(Number(form.virtual_transfer_price || 0) > 0))
    && !(f.key === 'virtual_value_2026_end' && !form.virtual_held_before_2027)
    && !(f.key === 'multi_home_surcharge' && tab === 'capital' && (form.asset_type || '주택') !== '주택')
    && !(['is_one_home', 'residence_years', 'acquired_in_adjusted_area'].includes(f.key) && tab === 'capital' && !['주택', '조합원입주권'].includes(form.asset_type || '주택'))
    && !(f.key === 'non_business_land' && form.asset_type !== '토지·건물')
    && !(f.key === 'unregistered' && ['주식', '파생상품', '신탁수익권'].includes(form.asset_type))
    && !(['pre_approval_gain', 'pre_approval_years'].includes(f.key) && form.asset_type !== '조합원입주권')
    && !(['stock_market', 'major_shareholder', 'sme'].includes(f.key) && form.asset_type !== '주식')
    && !(['simple_rate', 'simple_excess_rate'].includes(f.key) && tab === 'income' && (form.business_method || '장부') === '장부')
    && !(['standard_rate', 'major_expenses', 'double_entry'].includes(f.key) && tab === 'income' && form.business_method !== '기준경비율')
    && !(f.key === 'expense' && tab === 'income' && (form.business_method || '장부') !== '장부')
    && !(f.key === 'pension_age' && !(Number(form.private_pension || 0) > 0))
    && !(['misc_expense_rule', 'misc_expenses'].includes(f.key) && !(Number(form.misc_income || 0) > 0))
    && !(['rental_expenses', 'registered_rental'].includes(f.key) && !(Number(form.rental_income || 0) > 0))
    && !(f.key === 'daily_work_days' && !(Number(form.daily_wage || 0) > 0))
    && !(['is_minor', 'generation_skipping', 'marriage_birth'].includes(f.key) && form.relation && form.relation !== '직계존비속')
    && !(['prior_gift_taxable', 'prior_gift_tax'].includes(f.key) && tab === 'gift' && !(Number(form.prior_gifts_10y || 0) > 0))
    && !(['prior_gifts_taxable', 'prior_gift_tax', 'spouse_prior_gifts_taxable'].includes(f.key) && tab === 'inheritance' && !(Number(form.prior_gifts || 0) + Number(form.prior_gifts_non_heirs || 0) > 0))
    && !(f.key === 'spouse_inheritance' && form.has_spouse === false) && !(f.key === 'parents_count' && Number(form.children_count || 0) > 0)
    && !(f.key === 'skipped_generation_minor' && !(Number(form.skipped_generation_assets || 0) > 0)) && !(f.key === 'sincere_business' && (Number(form.wage_income || 0) > 0 || !(Number(form.income || 0) > 0))))
  return <main className="workspace-page">
    <header className="page-header"><div><p className="eyebrow">CALCULATION WORKSPACE</p><h1>세금 계산기</h1></div><span className="small muted">참고용 · 세율 및 적용 조건 확인 필요</span></header>
    <div className="page-scroll">
      <div className="calculator-tabs" aria-label="계산할 세목">{TABS.map(t => <button key={t.key} aria-pressed={tab === t.key} onClick={() => { invalidate(); setTab(t.key); setForm({ ...FORMS[t.key].defaults }) }}>{t.label}</button>)}</div>
      <div className="calculator-layout">
        <form className="calculation-form" ref={formElement} onSubmit={submit} noValidate>
          <div className="section-heading"><h2>계산 조건</h2><span className="unit-label">금액 입력: 만원</span></div>
          {tab === 'capital' && <p className="small muted">자산 1건 기준입니다. 1세대 1주택·중과·대주주 여부는 입력값을 따릅니다.</p>}
          {visible.map((field, i) => <div className="field" key={field.key}>
            {field.section && <p className="small muted">{field.section} — 신고·납부 기한을 넘긴 경우에만 고르세요.</p>}
            {field.type === 'checkbox' ? <label className="checkbox-field"><input type="checkbox" checked={!!form[field.key]} onChange={e => change(field.key, e.target.checked)} />{field.label}{field.hint && <span className="field-hint">{field.hint}</span>}</label>
              : <><label htmlFor={'calc-' + field.key}>{field.label}{field.required && <span className="required"> *</span>}</label>
                <div className="input-with-unit">{field.type === 'select'
                  ? <select id={'calc-' + field.key} value={form[field.key] || field.options[0]} onChange={e => change(field.key, e.target.value)}>{!field.options.includes(form[field.key]) && form[field.key] && <option value={form[field.key]} disabled>미지원 조건 — 변경 필요</option>}{field.options.map(v => <option key={v}>{v}</option>)}</select>
                  : field.type === 'date'
                  ? <input id={'calc-' + field.key} type="date" value={form[field.key] || ''} onChange={e => change(field.key, e.target.value)} aria-describedby={field.hint ? field.key + '-hint' : undefined} />
                  : <input ref={i === 0 ? firstInput : undefined} id={'calc-' + field.key} type="number" min="0" step={field.unit === '만원' ? '0.0001' : field.unit === '%' ? '0.1' : '1'} value={form[field.key] ?? ''} onChange={e => change(field.key, e.target.value)} placeholder={field.required ? '필수 입력' : '0'} required={field.required} aria-describedby={field.hint ? field.key + '-hint' : undefined} />}
                  {field.unit && <span>{field.unit}</span>}</div>{field.hint && <p className="field-hint" id={field.key + '-hint'}>{field.hint}</p>}</>}
          </div>)}
          <Notice>{error && <><span>{error.message}</span><br />세액을 산출하지 않았습니다. 0원이라는 뜻이 아닙니다.</>}</Notice>
          <button className="button calculate-submit" disabled={loading}>{loading ? <><span className="spinner" />계산 중…</> : error?.retryable ? '다시 계산하기' : '계산하기'}</button>
        </form>
        <div className="calculation-output">
          {result ? <><section className="condition-summary"><h2>이 결과의 입력 조건</h2><dl>{fields.filter(f => snapshot[f.key] !== undefined && snapshot[f.key] !== '').map(f => <div key={f.key}><dt>{f.label}</dt><dd>{f.type === 'checkbox' ? (snapshot[f.key] ? '예' : '아니오') : snapshot[f.key]} {f.unit || ''}</dd></div>)}</dl><button className="button secondary" onClick={() => firstInput.current?.focus()}>조건 수정</button></section>
            <ResultCard result={result} onAskAboutResult={onAskAboutResult ? () => onAskAboutResult(QUESTION_BUILDERS[tab](snapshot, result)) : undefined} /></>
            : <div className="empty-state" role="status"><Icon name="calculator" size={38} /><h2>{loading ? '계산 중입니다.' : error ? '계산을 완료하지 못했습니다.' : '조건을 입력하면 계산 과정을 보여드립니다.'}</h2><p>{error ? '입력 영역의 안내를 확인해 주세요.' : '산출 과정과 최종 금액을 함께 확인할 수 있습니다.'}</p></div>}
        </div>
      </div><p className="small muted">DB 세율·공제와 구현된 상수를 사용하는 단순 계산입니다. 최신 세법 준수 및 모든 예외 적용을 보장하지 않습니다.</p>
    </div>
  </main>
}

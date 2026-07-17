import { useEffect, useState } from 'react'
import { calcIncomeTax, calcCapitalGains, calcInheritance, calcGiftTax } from '../../api/calculatorApi'
import ResultCard from './ResultCard'

// 챗봇 계산기 엔진(app/services/calculator/engine.py _TOOLS)의 도구명 → 화면 탭 키
const TOOL_TO_TAB = {
  income_tax:    'income',
  capital_gains: 'capital',
  inheritance:   'inheritance',
  gift:          'gift',
}

const TABS = [
  { key: 'income',      label: '소득세',    icon: '💼' },
  { key: 'capital',     label: '양도소득세', icon: '🏠' },
  { key: 'inheritance', label: '상속세',    icon: '📜' },
  { key: 'gift',        label: '증여세',    icon: '🎁' },
]

const FORMS = {
  income: {
    apiFn: calcIncomeTax,
    fields: [
      { key: 'income',                   label: '총소득금액',    unit: '만원', required: true,  hint: '근로·사업·기타소득 합계' },
      { key: 'expense',                  label: '필요경비',      unit: '만원', required: false, hint: '사업자만 해당' },
      { key: 'personal_deduction_count', label: '기본공제 인원', unit: '명',   required: false, hint: '본인 포함 (기본 1명)' },
      { key: 'other_deductions',         label: '기타공제 합계', unit: '만원', required: false, hint: '의료비·교육비 등' },
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
      { key: 'asset_type',        label: '자산유형',    type: 'select', options: ['부동산', '주식', '기타'] },
      { key: 'is_one_home',       label: '1세대 1주택', type: 'checkbox', hint: '비과세 적용 여부' },
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
}

const toWon   = (v) => (parseInt(v) || 0) * 10_000
const toInt   = (v, def = 0) => parseInt(v) || def
const fromWon = (v) => String(Math.round((v || 0) / 10_000))
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
}

export default function CalculatorScreen({ initial, onInitialConsumed, onAskAboutResult }) {
  const [tab, setTab] = useState('income')
  const [form, setForm] = useState({ ...FORMS.income.defaults })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 챗봇에서 "계산기에서 조건 바꿔보기"로 넘어온 경우 해당 탭 + 입력값 프리필
  useEffect(() => {
    if (!initial) return
    const tabKey = TOOL_TO_TAB[initial.tool]
    if (tabKey) {
      setTab(tabKey)
      setForm(buildFormFromParams(tabKey, initial.params || {}))
      setResult(null)
      setError('')
    }
    onInitialConsumed?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial])

  const handleTabChange = (key) => {
    setTab(key)
    setForm({ ...FORMS[key].defaults })
    setResult(null)
    setError('')
  }

  const handleChange = (key, value) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const { apiFn, fields, toPayload } = FORMS[tab]

    const missing = fields.filter(f => f.required && !form[f.key])
    if (missing.length) {
      setError(`필수 항목을 입력하세요: ${missing.map(f => f.label).join(', ')}`)
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    try {
      const data = await apiFn(toPayload(form))
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const { fields } = FORMS[tab]
  const currentTab = TABS.find(t => t.key === tab)

  return (
    <main style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      background: 'var(--bg)', minWidth: 0, overflow: 'hidden',
    }}>
      {/* 헤더 */}
      <header style={{
        padding: '18px 32px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        background: 'rgba(24,28,39,.8)',
        backdropFilter: 'blur(8px)',
      }}>
        <span style={{ fontSize: 20 }}>{currentTab.icon}</span>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 17, fontWeight: 400, letterSpacing: '-0.3px' }}>
          세금 계산기
        </h1>
        <span style={{
          fontSize: 11, color: 'var(--text-muted)',
          background: 'var(--surface2)',
          border: '1px solid var(--border)',
          borderRadius: 6, padding: '2px 8px',
        }}>
          2024년 세법 기준
        </span>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* 세목 탭 */}
        <div style={{ display: 'flex', gap: 6 }}>
          {TABS.map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => handleTabChange(key)}
              style={{
                padding: '8px 16px',
                borderRadius: 9,
                border: '1px solid ' + (tab === key ? 'transparent' : 'var(--border)'),
                background: tab === key
                  ? 'linear-gradient(135deg, var(--accent), rgba(79,124,255,.7))'
                  : 'var(--surface)',
                color: tab === key ? '#fff' : 'var(--text-muted)',
                fontSize: 13, cursor: 'pointer',
                transition: 'all .15s',
                display: 'flex', alignItems: 'center', gap: 6,
                boxShadow: tab === key ? '0 3px 10px rgba(79,124,255,.3)' : 'none',
              }}
            >
              <span>{icon}</span>
              {label}
            </button>
          ))}
        </div>

        {/* 폼 + 결과 */}
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap' }}>

          {/* 폼 */}
          <form onSubmit={handleSubmit} style={{
            flex: '0 0 360px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(255,255,255,.02)',
            }}>
              <span>{currentTab.icon}</span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{currentTab.label} 계산</span>
            </div>
            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              {fields.map(field => (
                <FormField
                  key={field.key}
                  field={field}
                  value={form[field.key]}
                  onChange={handleChange}
                />
              ))}

              {error && (
                <div style={{
                  fontSize: 12, color: 'var(--danger)',
                  padding: '8px 12px',
                  background: 'rgba(255,92,92,.08)',
                  border: '1px solid rgba(255,92,92,.15)',
                  borderRadius: 8,
                }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                style={{
                  padding: '12px',
                  background: loading ? 'rgba(79,124,255,.4)' : 'var(--accent)',
                  color: '#fff',
                  border: 'none', borderRadius: 9,
                  fontSize: 14, fontWeight: 500,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'background .15s',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                }}
              >
                {loading && (
                  <span style={{
                    width: 14, height: 14,
                    border: '2px solid rgba(255,255,255,.3)',
                    borderTopColor: '#fff', borderRadius: '50%',
                    animation: 'spin .7s linear infinite',
                    display: 'inline-block',
                  }} />
                )}
                {loading ? '계산 중…' : '계산하기'}
              </button>
            </div>
          </form>

          {/* 결과 */}
          <div style={{ flex: 1, minWidth: 280 }}>
            {!result && !loading && (
              <div style={{
                color: 'var(--text-muted)', fontSize: 13,
                padding: '48px 20px', textAlign: 'center',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
              }}>
                <div style={{ fontSize: 28, marginBottom: 10, opacity: .3 }}>📊</div>
                금액을 입력하고 계산하기를 누르세요.
              </div>
            )}
            {result && (
              <ResultCard
                result={result}
                onAskAboutResult={
                  onAskAboutResult
                    ? () => onAskAboutResult(QUESTION_BUILDERS[tab](form, result))
                    : undefined
                }
              />
            )}
          </div>
        </div>

        <p style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, padding: '4px 0' }}>
          * 이 계산기는 참고용이며 법적 효력이 없습니다. 실제 세금은 개인 상황에 따라 다를 수 있으므로 세무사 상담을 권장합니다.
        </p>
      </div>
    </main>
  )
}

function FormField({ field, value, onChange }) {
  const labelStyle = {
    fontSize: 12, color: 'var(--text-muted)',
    marginBottom: 6, display: 'block', fontWeight: 500,
  }
  const inputStyle = {
    flex: 1,
    background: 'var(--surface2)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    padding: '9px 12px',
    color: 'var(--text)',
    fontSize: 14,
    outline: 'none',
    width: '100%',
    transition: 'border-color .15s, box-shadow .15s',
  }

  if (field.type === 'select') {
    return (
      <div>
        <label style={labelStyle}>{field.label}</label>
        <select
          value={value || field.options[0]}
          onChange={e => onChange(field.key, e.target.value)}
          style={{ ...inputStyle, cursor: 'pointer' }}
        >
          {field.options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    )
  }

  if (field.type === 'checkbox') {
    return (
      <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', padding: '4px 0' }}>
        <input
          type="checkbox"
          checked={!!value}
          onChange={e => onChange(field.key, e.target.checked)}
          style={{ width: 16, height: 16, cursor: 'pointer', accentColor: 'var(--accent)' }}
        />
        <span style={{ fontSize: 13 }}>{field.label}</span>
        {field.hint && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{field.hint}</span>}
      </label>
    )
  }

  return (
    <div>
      <label style={labelStyle}>
        {field.label}
        {field.required && <span style={{ color: 'var(--accent2)', marginLeft: 3 }}>*</span>}
        {field.hint && <span style={{ marginLeft: 6, fontWeight: 400, color: 'var(--text-muted)', fontSize: 11 }}>({field.hint})</span>}
      </label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          type="number"
          min={0}
          value={value ?? ''}
          onChange={e => onChange(field.key, e.target.value)}
          placeholder={field.required ? '필수' : '0'}
          style={inputStyle}
        />
        {field.unit && (
          <span style={{
            fontSize: 12, color: 'var(--text-muted)',
            whiteSpace: 'nowrap', flexShrink: 0,
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
            borderRadius: 6, padding: '9px 10px',
          }}>
            {field.unit}
          </span>
        )}
      </div>
    </div>
  )
}

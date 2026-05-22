import { useState } from 'react'
import { calcIncomeTax, calcCapitalGains, calcInheritance, calcGiftTax } from '../../api/calculatorApi'
import ResultCard from './ResultCard'

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
      { key: 'relation',        label: '증여자와의 관계',     type: 'select', options: ['직계존속', '직계비속', '배우자', '기타'] },
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

const toWon  = (v) => (parseInt(v) || 0) * 10_000
const toInt  = (v, def = 0) => parseInt(v) || def

export default function CalculatorScreen() {
  const [tab, setTab] = useState('income')
  const [form, setForm] = useState({ ...FORMS.income.defaults })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
            {result && <ResultCard result={result} />}
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

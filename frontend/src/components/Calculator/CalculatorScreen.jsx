import { useEffect, useRef, useState } from 'react'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from './forms'
import ResultCard from './ResultCard'
import Notice from '../ui/Notice'
import Icon from '../ui/Icon'
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
      if (key === 'capital' && initial.params?.asset_type && initial.params.asset_type !== '부동산') setError({ message: '현재 양도소득세는 부동산만 지원합니다. 조건을 다시 확인하세요.' })
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
    if (tab === 'capital' && payload.asset_type !== '부동산') { setError({ message: '현재 부동산만 지원합니다.' }); return }
    setLoading(true)
    try {
      const data = await apiFn(payload)
      if (version === revision.current) { setResult(data); setSnapshot({ ...form }) }
    } catch (e) { if (version === revision.current) setError({ message: e.message, retryable: e.retryable }) }
    finally { if (version === revision.current) setLoading(false) }
  }
  const fields = FORMS[tab].fields
  const visible = fields.filter(f => !(f.key === 'business_type' && !form.is_simplified) && !(f.key === 'days_late' && form.penalty_type !== '납부지연') && !(f.key === 'is_negligent' && form.penalty_type === '납부지연'))
  return <main className="workspace-page">
    <header className="page-header"><div><p className="eyebrow">CALCULATION WORKSPACE</p><h1>세금 계산기</h1></div><span className="small muted">참고용 · 세율 및 적용 조건 확인 필요</span></header>
    <div className="page-scroll">
      <div className="calculator-tabs" aria-label="계산할 세목">{TABS.map(t => <button key={t.key} aria-pressed={tab === t.key} onClick={() => { invalidate(); setTab(t.key); setForm({ ...FORMS[t.key].defaults }) }}>{t.label}</button>)}</div>
      <div className="calculator-layout">
        <form className="calculation-form" ref={formElement} onSubmit={submit} noValidate>
          <div className="section-heading"><h2>계산 조건</h2><span className="unit-label">금액 입력: 만원</span></div>
          {tab === 'capital' && <p className="small muted">부동산만 지원합니다. 주식·기타 자산과 비과세 판정은 지원하지 않습니다.</p>}
          {visible.map((field, i) => <div className="field" key={field.key}>
            {field.type === 'checkbox' ? <label className="checkbox-field"><input type="checkbox" checked={!!form[field.key]} onChange={e => change(field.key, e.target.checked)} />{field.label}{field.hint && <span className="field-hint">{field.hint}</span>}</label>
              : <><label htmlFor={'calc-' + field.key}>{field.label}{field.required && <span className="required"> *</span>}</label>
                <div className="input-with-unit">{field.type === 'select'
                  ? <select id={'calc-' + field.key} value={form[field.key] || field.options[0]} onChange={e => change(field.key, e.target.value)}>{!field.options.includes(form[field.key]) && form[field.key] && <option value={form[field.key]} disabled>미지원 조건 — 변경 필요</option>}{field.options.map(v => <option key={v}>{v}</option>)}</select>
                  : <input ref={i === 0 ? firstInput : undefined} id={'calc-' + field.key} type="number" min="0" step={field.unit === '만원' ? '0.0001' : '1'} value={form[field.key] ?? ''} onChange={e => change(field.key, e.target.value)} placeholder={field.required ? '필수 입력' : '0'} required={field.required} aria-describedby={field.hint ? field.key + '-hint' : undefined} />}
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

import { useEffect, useRef, useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import ResultCard from '../Calculator/ResultCard'
import { listCases, createCase, getCase, updateCaseFacts, updateCaseDocument,
  clearCaseDocument, calculateCase, ensureCaseConversation, deleteCase, reportUrl,
  listScenarios, saveScenario, deleteScenario, applyReviewedField } from '../../api/consultationCasesApi'
import { reviewDocument } from '../../api/documentReviewApi'
import { REVIEW_FIELDS } from '../Documents/reviewFields'
import './consultationCases.css'

const yearNow = new Date().getFullYear()
const todayLocal = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}` }
const kinds = [
  ['income_tax', '종합소득세', '귀속연도'], ['capital_gains', '양도소득세', '양도일'],
  ['inheritance', '상속세', '상속개시일'], ['gift', '증여세', '증여일'],
  ['vat', '부가가치세', '과세기간 종료일'], ['penalty_tax', '가산세', '위반·납부 기준일'],
]
const kindInfo = kind => kinds.find(item => item[0] === kind) || kinds[0]
const showValue = (q) => q.value == null ? '' : String(q.type === 'amount' ? q.value / 10000 : q.type === 'boolean' ? q.value : q.value)
const inputValue = (q, value, onChange, id, required = true) => q.type === 'choice' || q.type === 'boolean'
  ? <select id={id} required={required} value={value} onChange={e => onChange(e.target.value)}><option value="">선택해 주세요</option>
    {(q.type === 'boolean' ? [['true', '예'], ['false', '아니요']] : q.options.map(option => [option, option]))
      .map(([option, label]) => <option key={option} value={option}>{label}</option>)}</select>
  : <span className="input-with-unit"><input id={id} type="number" min={q.key === 'personal_deduction_count' ? '1' : '0'}
    step={q.type === 'amount' ? '0.0001' : '1'} required={required} value={value} onChange={e => onChange(e.target.value)} placeholder="숫자를 입력하세요" />
    <span>{q.type === 'amount' ? '만원' : q.unit || '건'}</span></span>
const statusText = { pending: '자료 확인 전', attached: '내 문서 연결됨', needs_recheck: '문서 변경·삭제 확인 필요', not_available: '자료 없음 기록됨' }

export default function CasesScreen({ library, onOpenDocuments, onOpenChat }) {
  const [items, setItems] = useState([]), [selectedId, setSelectedId] = useState(null), [current, setCurrent] = useState(null)
  const [creating, setCreating] = useState(false), [title, setTitle] = useState('종합소득세 상담')
  const [question, setQuestion] = useState(''), [taxYear, setTaxYear] = useState(yearNow - 1)
  const [kind, setKind] = useState('income_tax'), [referenceDate, setReferenceDate] = useState(todayLocal())
  const [answer, setAnswer] = useState(''), [editing, setEditing] = useState(false), [editFacts, setEditFacts] = useState({})
  const [filenames, setFilenames] = useState({}), [notes, setNotes] = useState({})
  const [scenarios, setScenarios] = useState([]), [scenarioName, setScenarioName] = useState('')
  const [leftScenario, setLeftScenario] = useState(''), [rightScenario, setRightScenario] = useState('')
  const [reviewValues, setReviewValues] = useState({})
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('')
  const requestId = useRef(0)

  const reloadList = async () => setItems(await listCases())
  useEffect(() => {
    let active = true
    listCases().then(rows => {
      if (!active) return
      setItems(rows); setSelectedId(rows[0]?.id || null); setLoading(false)
    }).catch(e => { if (active) { setError(e.message); setLoading(false) } })
    library.refresh()
    return () => { active = false; ++requestId.current }
  }, [])
  useEffect(() => {
    const seq = ++requestId.current
    if (!selectedId) { setCurrent(null); return }
    setCurrent(null)
    getCase(selectedId).then(data => { if (seq === requestId.current) setCurrent(data) })
      .catch(e => { if (seq === requestId.current) setError(e.message) })
  }, [selectedId])
  useEffect(() => {
    let active = true
    setScenarios([]); setReviewValues({})
    if (selectedId) listScenarios(selectedId).then(rows => {
      if (!active) return
      setScenarios(rows); setLeftScenario(rows[0]?.id || ''); setRightScenario(rows[1]?.id || '')
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [selectedId])
  const display = data => {
    setCurrent(data)
    setAnswer('')
    setEditFacts(Object.fromEntries(data.questions.map(q => [q.key, showValue(q)])))
  }
  const perform = async action => {
    if (busy) return
    setBusy(true); setError('')
    try { await action() }
    catch (e) { setError(e.message || '작업을 완료하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const create = e => {
    e.preventDefault()
    perform(async () => {
      const date = kind === 'income_tax' ? Number(taxYear) === yearNow
        ? todayLocal() : `${taxYear}-12-31` : referenceDate
      const data = await createCase({ kind, title: title.trim(), question: question.trim(),
        tax_year: kind === 'income_tax' ? Number(taxYear) : Number(date.slice(0, 4)), reference_date: date })
      await reloadList(); setSelectedId(data.id); display(data); setCreating(false); setQuestion('')
    })
  }
  const toFact = (q, text) => {
    if (text === '') return null
    if (q.type === 'choice') return text
    if (q.type === 'boolean') return text === 'true'
    const value = Number(text)
    const converted = q.type === 'amount' ? Math.round(value * 10000) : value
    if (!Number.isSafeInteger(converted) || converted < (q.key === 'personal_deduction_count' ? 1 : 0)) {
      throw new Error('금액은 0원 이상, 인원은 1명 이상의 정확한 값으로 입력해 주세요.')
    }
    return converted
  }
  const next = current?.questions.find(q => !q.answered)
  const saveAnswer = e => {
    e.preventDefault()
    perform(async () => display(await updateCaseFacts(current.id, { [next.key]: toFact(next, answer) })))
  }
  const saveEdits = e => {
    e.preventDefault()
    perform(async () => {
      const changes = Object.fromEntries(current.questions.map(q => [q.key, toFact(q, editFacts[q.key] ?? '')]))
      display(await updateCaseFacts(current.id, changes)); setEditing(false)
    })
  }
  const attach = slot => perform(async () => {
    if (!filenames[slot]) throw new Error('연결할 문서를 선택해 주세요.')
    display(await updateCaseDocument(current.id, slot, { status: 'attached', filename: filenames[slot] }))
  })
  const markMissing = slot => perform(async () => {
    if (!notes[slot]?.trim()) throw new Error('자료가 없는 이유를 입력해 주세요.')
    display(await updateCaseDocument(current.id, slot, { status: 'not_available', note: notes[slot].trim() }))
  })
  const openChat = mode => perform(async () => {
    const data = await ensureCaseConversation(current.id)
    display(data)
    const factText = current.questions.map(q => `${q.question} ${q.value}${q.type === 'amount' ? '원' : ''}`).join('; ')
    const basisQuestion = `${current.kind_label} 참고 계산을 검토해 주세요. 자료 조회 기준일은 ${current.reference_date}입니다. 입력: ${factText}. 계산기 결과는 ${current.calculation?.result?.final_tax}원이며 DB 자료 시행일은 ${(current.calculation?.result?.basis?.effective_dates || []).join(', ') || '확인되지 않음'}입니다. 계산 근거의 공식 원문과 실제 적용 가능 시점을 확인하고, 확정할 수 없는 부분은 명시해 주세요.`
    const initialQuestion = `${data.kind_label} 상담입니다. 자료 조회 기준일은 ${data.reference_date}입니다. ${data.question}`
    onOpenChat(data.conversation_id, mode === 'basis' ? basisQuestion : !data.has_chat ? initialQuestion : null)
  })
  const remove = id => {
    if (!window.confirm('상담 작업 공간을 삭제할까요? 연결된 채팅 대화와 내 문서는 유지됩니다.')) return
    perform(async () => {
      await deleteCase(id)
      const rows = await listCases(); setItems(rows)
      setSelectedId(selected => selected === id ? (rows[0]?.id || null) : selected)
    })
  }
  const loadReviewed = filename => perform(async () => {
    const result = await reviewDocument(filename)
    setReviewValues(previous => ({ ...previous, [filename]: result.fields }))
  })
  const saveCurrentScenario = () => perform(async () => {
    await saveScenario(current.id, scenarioName.trim())
    const rows = await listScenarios(current.id)
    setScenarios(rows); setLeftScenario(rows[0]?.id || ''); setRightScenario(rows[1]?.id || '')
    setScenarioName('')
  })
  const removeScenario = id => perform(async () => {
    await deleteScenario(current.id, id)
    const rows = await listScenarios(current.id)
    setScenarios(rows); setLeftScenario(rows[0]?.id || ''); setRightScenario(rows[1]?.id || '')
  })
  const left = scenarios.find(item => item.id === leftScenario)
  const right = scenarios.find(item => item.id === rightScenario)
  const won = value => `${Number(value || 0).toLocaleString('ko-KR')}원`

  return <main className="workspace-page">
    <header className="page-header"><div><p className="eyebrow">CONSULTATION WORKSPACE</p><h1>상담 작업</h1></div>
      <button className="button" onClick={() => setCreating(v => !v)}><Icon name="plus" size={17} />새 상담</button></header>
    <div className="page-scroll case-scroll">
      <Notice>{error}</Notice>
      {creating && <form className="case-create" onSubmit={create}>
        <h2>세무 상담 시작</h2><p className="small muted">세목을 고른 뒤 필요한 계산 조건을 차례로 확인합니다.</p>
        <label>세목<select value={kind} onChange={e => { const selected = e.target.value; setKind(selected); setTitle(`${kindInfo(selected)[1]} 상담`) }}>
          {kinds.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>상담 제목<input required maxLength="80" value={title} onChange={e => setTitle(e.target.value)} /></label>
        {kind === 'income_tax' ? <label>귀속연도<input required type="number" min="2000" max={yearNow} value={taxYear} onChange={e => setTaxYear(e.target.value)} /></label>
          : <label>{kindInfo(kind)[2]} · 자료 조회 기준일<input required type="date" min="2000-01-01" max={todayLocal()} value={referenceDate} onChange={e => setReferenceDate(e.target.value)} /></label>}
        <label>궁금한 내용<textarea required maxLength="5000" rows="3" value={question} onChange={e => setQuestion(e.target.value)} placeholder="예: 사업소득이 있는데 예상 세액과 적용 근거가 궁금합니다." /></label>
        <button className="button" disabled={busy}>상담 만들기</button>
      </form>}
      {loading && <p role="status">상담 목록을 불러오고 있습니다…</p>}
      {!loading && <div className="case-layout">
        <aside className="case-list" aria-label="상담 목록">
          <h2>진행 중인 상담 <span className="small muted">{items.length}건</span></h2>
          {!items.length && <p className="small muted">새 상담을 만들면 이곳에 저장됩니다.</p>}
          {items.map(item => <div className={'case-list-item ' + (item.id === selectedId ? 'selected' : '')} key={item.id}>
            <button onClick={() => { setSelectedId(item.id); setEditing(false); setError('') }} aria-current={item.id === selectedId ? 'true' : undefined}>
              <strong>{item.title}</strong><span>{item.kind_label || kindInfo(item.kind)[1]} · 질문 {item.answered}/{item.question_count || 4} 확인</span>
              <small>{item.has_calculation ? '계산 결과 저장됨' : '계산 전'}</small></button>
            <button className="icon-button" aria-label={`${item.title} 삭제`} onClick={() => remove(item.id)} disabled={busy}><Icon name="trash" size={16} /></button>
          </div>)}
        </aside>
        <div className="case-detail">
          {selectedId && !current && <p role="status">상담 내용을 불러오고 있습니다…</p>}
          {!selectedId && <div className="empty-state"><Icon name="book" size={32} /><h2>상담을 시작해 보세요.</h2><p>질문과 계산 조건, 준비한 서류를 한곳에서 관리합니다.</p></div>}
          {current && <>
            <section className="case-card"><div className="case-head"><div><p className="eyebrow">{current.kind_label} · {current.kind === 'income_tax' ? `${current.tax_year}년 귀속` : `${current.reference_date} 조회 기준`}</p><h2>{current.title}</h2></div>
              <button className="button secondary" disabled={busy} onClick={() => openChat('initial')}><Icon name="chat" size={17} />{current.has_chat ? '대화 계속' : '질문 보내기'}</button></div>
              <p className="case-question">{current.question}</p><p className="small muted">이 상담에서 확인한 계산 조건과 업로드 문서는 로그인한 사용자에게만 연결됩니다.</p></section>
            <section className="case-card"><h2>상담 보고서</h2><p className="small muted">현재 저장된 입력·서류 상태·계산 과정·표시된 근거를 PDF로 내려받습니다.</p>
              <a className="button secondary" href={reportUrl(current.id)} download>보고서 PDF 다운로드</a></section>
            <section className="case-card"><div className="section-heading"><h2>1. 필요한 정보 확인</h2><span>{current.questions.filter(q => q.answered).length}/{current.questions.length} 확인</span></div>
              {next ? <form className="case-answer" onSubmit={saveAnswer} key={next.key}>
                <label htmlFor="case-next-answer">{next.question}</label>{inputValue(next, answer, setAnswer, 'case-next-answer')}
                <button className="button" disabled={busy}>저장하고 다음 질문</button></form>
                : <p className="case-complete"><Icon name="check" size={18} />계산에 필요한 조건을 모두 확인했습니다.</p>}
              {current.questions.some(q => q.answered) && <><button className="text-button" onClick={() => { setEditFacts(Object.fromEntries(current.questions.map(q => [q.key, showValue(q)]))); setEditing(v => !v) }}>입력한 정보 수정</button>
                {editing && <form className="case-edit-facts" onSubmit={saveEdits}>{current.questions.map(q => <label key={q.key}>{q.question}{inputValue(q, editFacts[q.key] ?? '', value => setEditFacts(prev => ({ ...prev, [q.key]: value })), undefined, false)}</label>)}
                  <button className="button secondary" disabled={busy}>변경 저장</button></form>}</>}
              <p className="small muted">금액은 만원 단위로 입력하며 0원인 항목도 직접 확인합니다. 계산 결과는 조건을 바꾸면 초기화됩니다.</p></section>
            <section className="case-card"><div className="section-heading"><h2>2. 서류 체크리스트</h2><button className="button secondary" onClick={onOpenDocuments}><Icon name="file" size={16} />내 문서로 이동</button></div>
              <p className="small muted">업로드한 PDF를 항목에 연결하거나 자료가 없는 이유를 기록하세요. 문서 내용에서 금액을 자동 확정하지 않습니다.</p>
              <Notice onRetry={library.refresh}>{library.error}</Notice>
              <div className="case-documents">{current.checklist.map(item => <div className="case-document" key={item.key}>
                <div><h3>{item.title} <span className="small muted">{item.needed ? '확인 권장' : '현재 입력에는 해당 없음'}</span></h3><p className="small muted">{item.prompt}</p>
                  <p className={'case-doc-status ' + (item.status === 'needs_recheck' ? 'warning' : '')}>{statusText[item.status]}{item.filename ? ` · ${item.filename}` : ''}{item.note ? ` · ${item.note}` : ''}</p></div>
                <div className="case-document-actions"><select aria-label={`${item.title} 연결 문서`} value={filenames[item.key] || ''} onChange={e => setFilenames(prev => ({ ...prev, [item.key]: e.target.value }))}>
                  <option value="">내 문서 선택</option>{library.documents.map(doc => <option key={doc.filename} value={doc.filename}>{doc.filename}</option>)}</select>
                  <button className="button secondary" disabled={busy || !filenames[item.key]} onClick={() => attach(item.key)}>연결</button></div>
                <div className="case-document-actions"><input aria-label={`${item.title} 자료 없음 이유`} maxLength="500" value={notes[item.key] || ''} placeholder="자료가 없다면 이유를 기록" onChange={e => setNotes(prev => ({ ...prev, [item.key]: e.target.value }))} />
                  <button className="button secondary" disabled={busy || !notes[item.key]?.trim()} onClick={() => markMissing(item.key)}>자료 없음</button>
                  {item.status !== 'pending' && <button className="text-button" disabled={busy} onClick={() => perform(async () => display(await clearCaseDocument(current.id, item.key)))}>초기화</button>}</div>
                {item.status === 'attached' && <div className="case-reviewed-values"><button className="text-button" disabled={busy} onClick={() => loadReviewed(item.filename)}>확인한 문서 금액 불러오기</button>
                  {reviewValues[item.filename] && (Object.entries(reviewValues[item.filename]).length
                    ? Object.entries(reviewValues[item.filename]).filter(([key]) => current.questions.some(q => q.key === key && q.type === 'amount')).map(([key, value]) =>
                      <button key={key} className="button secondary" disabled={busy} onClick={() => perform(async () => {
                        display(await applyReviewedField(current.id, item.filename, key)); await reloadList()
                      })}>{REVIEW_FIELDS[key] || key} {won(value.value)} → 상담 입력에 적용</button>)
                    : <p className="small muted">저장된 검토값이 없습니다. 내 문서에서 원본을 검토해 주세요.</p>)}</div>}
              </div>)}</div></section>
            <section className="case-card"><div className="section-heading"><h2>3. 계산과 근거</h2></div>
              <p className="small muted">{current.reference_date} 이전의 DB 세율·공제 자료로 단순 계산합니다. 코드에 고정된 공제율·계산식도 포함되어 있어 선택 날짜의 법적 적용을 보증하지 않으며 실제 신고세액을 확정하지 않습니다.</p>
              {current.checklist.some(item => item.needed && item.status === 'pending') && <p className="case-warning">확인 권장 서류가 남아 있습니다. 자료 없이 계산하면 결과의 근거를 별도로 검토하세요.</p>}
              {current.checklist.some(item => item.needed && item.status === 'needs_recheck') && <p className="case-warning">연결된 문서가 교체되거나 삭제되었습니다. 서류를 다시 확인해 주세요.</p>}
              <button className="button" disabled={busy || !!next} onClick={() => perform(async () => { display(await calculateCase(current.id)); await reloadList() })}>
                <Icon name="calculator" size={17} />{current.calculation ? '다시 계산하기' : `${current.kind_label} 계산하기`}</button>
              {current.calculation && <><p className="small muted case-result-meta">{current.reference_date} 조회 기준 · {new Date(current.calculation.calculated_at).toLocaleString('ko-KR')} 계산</p>
                <ResultCard result={current.calculation.result} onAskAboutResult={() => openChat('basis')} /></>}
            </section>
            <section className="case-card"><div className="section-heading"><h2>4. 계산 시나리오 비교</h2><span>{scenarios.length}/30 저장</span></div>
              <p className="small muted">현재 계산 결과를 저장한 뒤 입력값을 바꿔 다시 계산하면 두 결과를 비교할 수 있습니다.</p>
              <div className="case-scenario-save"><input aria-label="시나리오 이름" maxLength="80" value={scenarioName} onChange={e => setScenarioName(e.target.value)} placeholder="예: 경비 반영 전" />
                <button className="button secondary" disabled={busy || !current.calculation || !scenarioName.trim()} onClick={saveCurrentScenario}>현재 계산 저장</button></div>
              {scenarios.map(item => <div className="case-scenario-row" key={item.id}><span>{item.name} · {won(item.result.final_tax)} · {item.reference_date}</span>
                <button className="text-button" disabled={busy} onClick={() => removeScenario(item.id)}>삭제</button></div>)}
              {scenarios.length >= 2 && <><div className="case-scenario-selectors"><label>비교 A<select value={leftScenario} onChange={e => setLeftScenario(e.target.value)}>{scenarios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>비교 B<select value={rightScenario} onChange={e => setRightScenario(e.target.value)}>{scenarios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
                {left && right && left.id !== right.id && <div className="case-scenario-diff"><strong>결과 차이 (B - A): {won(right.result.final_tax - left.result.final_tax)}</strong>
                  <table><thead><tr><th>계산 단계</th><th>A</th><th>B</th></tr></thead><tbody>{[...new Set([...left.result.steps, ...right.result.steps].map(step => step.label))].map(label => <tr key={label}><td>{label}</td><td>{left.result.steps.find(step => step.label === label) ? won(left.result.steps.find(step => step.label === label).amount) : '—'}</td><td>{right.result.steps.find(step => step.label === label) ? won(right.result.steps.find(step => step.label === label).amount) : '—'}</td></tr>)}</tbody></table>
                  <p className="small muted">두 결과의 조회 기준일 {left.reference_date} / {right.reference_date}. 조건이 다르면 단계 이름과 근거도 함께 확인하세요.</p></div>}</>}
            </section>
          </>}
        </div>
      </div>}
    </div>
  </main>
}

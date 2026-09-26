import { useEffect, useRef, useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import ResultCard from '../Calculator/ResultCard'
import { listCases, createCase, getCase, updateCaseFacts, updateCaseDocument,
  clearCaseDocument, calculateCase, ensureCaseConversation, deleteCase } from '../../api/consultationCasesApi'
import './consultationCases.css'

const yearNow = new Date().getFullYear()
const moneyFields = new Set(['income', 'expense', 'other_deductions'])
const showValue = (key, value) => value == null ? '' : String(moneyFields.has(key) ? value / 10000 : value)
const statusText = { pending: '자료 확인 전', attached: '내 문서 연결됨', needs_recheck: '문서 변경·삭제 확인 필요', not_available: '자료 없음 기록됨' }

export default function CasesScreen({ library, onOpenDocuments, onOpenChat }) {
  const [items, setItems] = useState([]), [selectedId, setSelectedId] = useState(null), [current, setCurrent] = useState(null)
  const [creating, setCreating] = useState(false), [title, setTitle] = useState('종합소득세 상담')
  const [question, setQuestion] = useState(''), [taxYear, setTaxYear] = useState(yearNow - 1)
  const [answer, setAnswer] = useState(''), [editing, setEditing] = useState(false), [editFacts, setEditFacts] = useState({})
  const [filenames, setFilenames] = useState({}), [notes, setNotes] = useState({})
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
  const display = data => {
    setCurrent(data)
    setAnswer('')
    setEditFacts(Object.fromEntries(data.questions.map(q => [q.key, showValue(q.key, q.value)])))
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
      const data = await createCase({ title: title.trim(), question: question.trim(), tax_year: Number(taxYear) })
      await reloadList(); setSelectedId(data.id); display(data); setCreating(false); setQuestion('')
    })
  }
  const toFact = (key, text) => {
    if (text === '') return null
    const value = Number(text)
    const converted = moneyFields.has(key) ? Math.round(value * 10000) : value
    if (!Number.isSafeInteger(converted) || converted < (key === 'personal_deduction_count' ? 1 : 0)) {
      throw new Error('금액은 0원 이상, 인원은 1명 이상의 정확한 값으로 입력해 주세요.')
    }
    return converted
  }
  const next = current?.questions.find(q => !q.answered)
  const saveAnswer = e => {
    e.preventDefault()
    perform(async () => display(await updateCaseFacts(current.id, { [next.key]: toFact(next.key, answer) })))
  }
  const saveEdits = e => {
    e.preventDefault()
    perform(async () => {
      const changes = Object.fromEntries(current.questions.map(q => [q.key, toFact(q.key, editFacts[q.key] ?? '')]))
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
    const facts = current.facts
    const basisQuestion = `${current.tax_year}년 귀속 종합소득세 참고 계산을 검토해 주세요. 총수입 ${facts.income}원, 필요경비 ${facts.expense}원, 기본공제 인원 ${facts.personal_deduction_count}명, 기타 소득공제 ${facts.other_deductions}원입니다. 계산기 결과는 ${current.calculation?.result?.final_tax}원이며 사용한 DB 자료의 시행일은 ${(current.calculation?.result?.basis?.effective_dates || []).join(', ') || '확인되지 않음'}입니다. 계산에 표시된 근거 조문 원문과 이 귀속연도에 적용 가능한지 확인하고, 확인할 수 없는 부분은 명시해 주세요.`
    onOpenChat(data.conversation_id, mode === 'basis' ? basisQuestion : !data.has_chat ? data.question : null)
  })
  const remove = id => {
    if (!window.confirm('상담 작업 공간을 삭제할까요? 연결된 채팅 대화와 내 문서는 유지됩니다.')) return
    perform(async () => {
      await deleteCase(id)
      const rows = await listCases(); setItems(rows)
      setSelectedId(selected => selected === id ? (rows[0]?.id || null) : selected)
    })
  }

  return <main className="workspace-page">
    <header className="page-header"><div><p className="eyebrow">CONSULTATION WORKSPACE</p><h1>상담 작업</h1></div>
      <button className="button" onClick={() => setCreating(v => !v)}><Icon name="plus" size={17} />새 상담</button></header>
    <div className="page-scroll case-scroll">
      <Notice>{error}</Notice>
      {creating && <form className="case-create" onSubmit={create}>
        <h2>종합소득세 상담 시작</h2><p className="small muted">질문을 기록하고 필요한 계산 조건을 차례로 확인합니다.</p>
        <label>상담 제목<input required maxLength="80" value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>귀속연도<input required type="number" min="2000" max={yearNow} value={taxYear} onChange={e => setTaxYear(e.target.value)} /></label>
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
              <strong>{item.title}</strong><span>{item.tax_year}년 귀속 · 질문 {item.answered}/4 확인</span>
              <small>{item.has_calculation ? '계산 결과 저장됨' : '계산 전'}</small></button>
            <button className="icon-button" aria-label={`${item.title} 삭제`} onClick={() => remove(item.id)} disabled={busy}><Icon name="trash" size={16} /></button>
          </div>)}
        </aside>
        <div className="case-detail">
          {selectedId && !current && <p role="status">상담 내용을 불러오고 있습니다…</p>}
          {!selectedId && <div className="empty-state"><Icon name="book" size={32} /><h2>상담을 시작해 보세요.</h2><p>질문과 계산 조건, 준비한 서류를 한곳에서 관리합니다.</p></div>}
          {current && <>
            <section className="case-card"><div className="case-head"><div><p className="eyebrow">{current.tax_year}년 귀속 · 종합소득세</p><h2>{current.title}</h2></div>
              <button className="button secondary" disabled={busy} onClick={() => openChat('initial')}><Icon name="chat" size={17} />{current.has_chat ? '대화 계속' : '질문 보내기'}</button></div>
              <p className="case-question">{current.question}</p><p className="small muted">이 상담에서 확인한 계산 조건과 업로드 문서는 로그인한 사용자에게만 연결됩니다.</p></section>
            <section className="case-card"><div className="section-heading"><h2>1. 필요한 정보 확인</h2><span>{current.questions.filter(q => q.answered).length}/4 확인</span></div>
              {next ? <form className="case-answer" onSubmit={saveAnswer} key={next.key}>
                <label htmlFor="case-next-answer">{next.question}</label><div className="input-with-unit"><input id="case-next-answer" type="number" min={next.key === 'personal_deduction_count' ? '1' : '0'}
                  step={next.unit === '원' ? '0.0001' : '1'} required value={answer} onChange={e => setAnswer(e.target.value)} placeholder="숫자를 입력하세요" />
                  <span>{next.unit === '원' ? '만원' : '명'}</span></div><button className="button" disabled={busy}>저장하고 다음 질문</button></form>
                : <p className="case-complete"><Icon name="check" size={18} />계산에 필요한 조건을 모두 확인했습니다.</p>}
              {current.questions.some(q => q.answered) && <><button className="text-button" onClick={() => { setEditFacts(Object.fromEntries(current.questions.map(q => [q.key, showValue(q.key, q.value)]))); setEditing(v => !v) }}>입력한 정보 수정</button>
                {editing && <form className="case-edit-facts" onSubmit={saveEdits}>{current.questions.map(q => <label key={q.key}>{q.question}<span className="input-with-unit"><input type="number" min={q.key === 'personal_deduction_count' ? '1' : '0'} step={q.unit === '원' ? '0.0001' : '1'}
                    value={editFacts[q.key] ?? ''} onChange={e => setEditFacts(prev => ({ ...prev, [q.key]: e.target.value }))} /><span>{q.unit === '원' ? '만원' : '명'}</span></span></label>)}
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
              </div>)}</div></section>
            <section className="case-card"><div className="section-heading"><h2>3. 계산과 근거</h2></div>
              <p className="small muted">선택한 귀속연도 말일 이전의 DB 세율·공제 자료로 단순 계산합니다. 자료의 시행일과 귀속연도가 다를 수 있으며 실제 신고세액을 확정하지 않습니다.</p>
              {current.checklist.some(item => item.needed && item.status === 'pending') && <p className="case-warning">확인 권장 서류가 남아 있습니다. 자료 없이 계산하면 결과의 근거를 별도로 검토하세요.</p>}
              {current.checklist.some(item => item.needed && item.status === 'needs_recheck') && <p className="case-warning">연결된 문서가 교체되거나 삭제되었습니다. 서류를 다시 확인해 주세요.</p>}
              <button className="button" disabled={busy || !!next} onClick={() => perform(async () => { display(await calculateCase(current.id)); await reloadList() })}>
                <Icon name="calculator" size={17} />{current.calculation ? '다시 계산하기' : '종합소득세 계산하기'}</button>
              {current.calculation && <><p className="small muted case-result-meta">{current.calculation.tax_year}년 귀속 입력 · {new Date(current.calculation.calculated_at).toLocaleString('ko-KR')} 계산</p>
                <ResultCard result={current.calculation.result} onAskAboutResult={() => openChat('basis')} /></>}
            </section>
          </>}
        </div>
      </div>}
    </div>
  </main>
}

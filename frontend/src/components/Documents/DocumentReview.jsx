import { useEffect, useState } from 'react'
import { originalPdfUrl, reviewDocument, saveDocumentReview } from '../../api/documentReviewApi'
import { REVIEW_FIELDS } from './reviewFields'
import Notice from '../ui/Notice'
import './documentReview.css'

export default function DocumentReview({ filename, onBack }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [field, setField] = useState('income'), [value, setValue] = useState(''), [page, setPage] = useState(1)
  const [dateValue, setDateValue] = useState('')
  const [note, setNote] = useState(''), [selectedPage, setSelectedPage] = useState(1)
  useEffect(() => {
    let active = true
    reviewDocument(filename).then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [filename])
  const choose = candidate => {
    setPage(candidate.page); setSelectedPage(candidate.page)
    if (candidate.type === 'amount') setValue(String(candidate.value))
    else setDateValue(candidate.value)
    setNote(candidate.context)
  }
  const persist = async (fields, dates = data.dates) => {
    setBusy(true); setError('')
    try { setData(await saveDocumentReview(filename, fields, dates, data.sha256, data.reviewed_at)) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const confirm = event => {
    event.preventDefault()
    const amount = Number(value)
    if (!Number.isSafeInteger(amount) || amount < 0) { setError('금액을 0원 이상의 정수로 입력해 주세요.'); return }
    persist({ ...data.fields, [field]: { value: amount, page: Number(page), note: note.slice(0, 300) } })
  }
  const confirmDate = event => {
    event.preventDefault()
    if (!dateValue) { setError('원본에서 확인한 날짜를 입력해 주세요.'); return }
    persist(data.fields, [...data.dates, { value: dateValue, page: Number(page), note: note.slice(0, 300) }])
  }
  return <main className="workspace-page review-page">
    <header className="page-header"><div><p className="eyebrow">DOCUMENT REVIEW</p><h1>{filename}</h1></div>
      <button className="button secondary" onClick={onBack}>문서함으로 돌아가기</button></header>
    <div className="page-scroll"><Notice>{error}</Notice>
      <p className="small muted">왼쪽 원본과 오른쪽 추출 후보를 대조한 뒤 금액을 직접 확정하세요. 추출 후보는 계산에 자동 반영되지 않습니다.</p>
      {data ? <div className="review-layout">
        <section className="review-source"><h2>원본 PDF · {selectedPage}쪽</h2>
          <iframe title={`${filename} 원본 PDF`} key={selectedPage} src={`${originalPdfUrl(filename)}#page=${selectedPage}`} />
          <a href={originalPdfUrl(filename)} target="_blank" rel="noopener noreferrer">새 창에서 원본 열기 ↗</a></section>
        <section className="review-values"><h2>확인할 항목</h2>
          <form onSubmit={confirm} className="review-form">
            <label>계산 항목<select value={field} onChange={e => setField(e.target.value)}>{Object.entries(REVIEW_FIELDS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
            <label>확인한 금액(원)<input type="number" min="0" step="1" required value={value} onChange={e => setValue(e.target.value)} /></label>
            <label>원본 페이지<input type="number" min="1" step="1" required value={page} onChange={e => { setPage(e.target.value); setSelectedPage(Number(e.target.value) || 1) }} /></label>
            <label>확인 메모<input maxLength="300" value={note} onChange={e => setNote(e.target.value)} /></label>
            <button className="button" disabled={busy}>검토값 저장</button>
          </form>
          <form onSubmit={confirmDate} className="review-form"><h3>확인한 날짜</h3>
            <label>원본 날짜<input type="date" required value={dateValue} onChange={e => setDateValue(e.target.value)} /></label>
            <p className="small muted">현재 선택한 {page}쪽을 근거로 저장합니다. 상담 조회 기준일은 자동 변경되지 않습니다.</p>
            <button className="button secondary" disabled={busy}>날짜 저장</button></form>
          <h3>저장한 검토값</h3>
          {Object.entries(data.fields).length ? Object.entries(data.fields).map(([key, item]) => <div className="review-confirmed" key={key}>
            <div><strong>{REVIEW_FIELDS[key] || key}: {item.value.toLocaleString('ko-KR')}원</strong><small>{item.page}쪽 · {item.note || '메모 없음'}</small></div>
            <button className="text-button" onClick={() => persist(Object.fromEntries(Object.entries(data.fields).filter(([saved]) => saved !== key)))} disabled={busy}>삭제</button>
          </div>) : <p className="small muted">아직 확인한 금액이 없습니다.</p>}
          {data.dates.map((item, index) => <div className="review-confirmed" key={`${item.value}-${index}`}>
            <div><strong>확인 날짜: {item.value}</strong><small>{item.page}쪽 · {item.note || '메모 없음'}</small></div>
            <button className="text-button" disabled={busy} onClick={() => persist(data.fields, data.dates.filter((_, saved) => saved !== index))}>삭제</button>
          </div>)}
          <h3>문서에서 찾은 후보 · 최대 150개</h3>
          {data.candidates.length ? <div className="review-candidates">{data.candidates.map((candidate, index) => <button type="button" key={`${candidate.page}-${index}`} onClick={() => choose(candidate)}>
            <strong>{candidate.display}</strong><span>{candidate.page}쪽 · {candidate.context}</span></button>)}</div>
            : <p className="small muted">금액·날짜 후보를 찾지 못했습니다. 원문을 보고 직접 입력할 수 있습니다.</p>}
        </section>
      </div> : !error && <p role="status">문서를 불러오고 있습니다…</p>}
    </div>
  </main>
}

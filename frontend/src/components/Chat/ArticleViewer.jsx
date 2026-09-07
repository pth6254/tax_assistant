import { useEffect, useRef, useState } from 'react'
import { fetchLawArticle } from '../../api/lawApi'
import { errorMessage } from '../../api/http'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
export default function ArticleViewer({ lawName, articleNo, onClose }) {
  const [article, setArticle] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0), [reference, setReference] = useState(articleNo), [query, setQuery] = useState(articleNo)
  const panel = useRef(), highlight = useRef()
  useEffect(() => { setReference(articleNo); setQuery(articleNo) }, [lawName, articleNo])
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setArticle(null)
    fetchLawArticle(lawName, query).then(data => { if (active) setArticle(data) })
      .catch(e => { if (active) setError(errorMessage(e, '조문을 불러오지 못했습니다.')) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [lawName, query, revision])
  useEffect(() => { panel.current?.querySelector('button')?.focus() }, [])
  useEffect(() => { highlight.current?.scrollIntoView({ block: 'nearest' }) }, [article])
  const target = article?.target, full = article?.article_text || '', excerpt = target?.exists ? target.text : null
  const at = excerpt ? full.indexOf(excerpt) : -1
  const exact = at >= 0 && full.indexOf(excerpt, at + 1) < 0
  const safeUrl = /^https?:\/\//i.test(article?.source_url || '') ? article.source_url : null
  return <aside ref={panel} className="source-panel" aria-label="조문 원문" onKeyDown={e => {
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    if (e.key === 'Tab' && window.matchMedia('(max-width: 1100px)').matches) {
      const focusable = [...panel.current.querySelectorAll('button,input,a[href]')].filter(el => !el.disabled)
      const first = focusable[0], last = focusable.at(-1)
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
    }
  }}>
    <header className="source-header"><div><p className="eyebrow">SOURCE DOCUMENT</p><h2>조문 원문</h2></div><button className="icon-button" aria-label="닫기" onClick={onClose}><Icon name="close" /></button></header>
    <form className="reference-form" onSubmit={e => { e.preventDefault(); if (reference.trim()) { setQuery(reference.trim()); setRevision(n => n + 1) } }}><label htmlFor="law-reference">조·항·호·목으로 조회</label><div><input id="law-reference" value={reference} onChange={e => setReference(e.target.value)} placeholder="제59조의4 제9항 제2호 가목" /><button className="button secondary" disabled={loading || !reference.trim()}>조회</button></div></form>
    <div className="source-scroll">
      {loading && <p role="status" className="muted">원문을 불러오고 있습니다…</p>}
      <Notice onRetry={() => setRevision(n => n + 1)}>{error}</Notice>
      {article && <>
        <p className="source-law">{article.law_name} · {article.law_type || '저장 자료'}</p>
        <h3>{article.article_no} {article.article_title && '[' + article.article_title + ']'}</h3>
        <div className="source-dates"><span>시행일: {article.effective_date || '정보 없음'}</span><span>공포일: {article.amendment_date || '정보 없음'}</span></div>
        {target && !target.exists && <Notice>{target.detail || '요청한 항·호·목을 본문에서 확인하지 못했습니다.'}</Notice>}
        {excerpt && !exact && <section className="target-excerpt" ref={highlight}><strong>요청한 부분 · 서버에서 추출</strong><p>{excerpt}</p></section>}
        <div className="source-text">{exact ? <>{full.slice(0, at)}<mark ref={highlight}>{excerpt}</mark>{full.slice(at + excerpt.length)}</> : full}</div>
        {safeUrl && <a className="source-external" href={safeUrl} target="_blank" rel="noreferrer">공식 원문에서 확인 ↗</a>}
        <p className="small muted">저장된 원문 조회이며, 답변 전체의 법적 타당성을 보증하지 않습니다.</p>
      </>}
    </div>
  </aside>
}

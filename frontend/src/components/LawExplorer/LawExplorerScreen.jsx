import { useEffect, useState } from 'react'
import { explorerLaws, explorerArticle, explorerCompare } from '../../api/lawExplorerApi'
import Notice from '../ui/Notice'
import './lawExplorer.css'

const localDate = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}` }

export default function LawExplorerScreen() {
  const [laws, setLaws] = useState([]), [lawId, setLawId] = useState('')
  const [articleNo, setArticleNo] = useState('제1조'), [asOf, setAsOf] = useState(localDate())
  const [leftDate, setLeftDate] = useState('2024-01-01'), [rightDate, setRightDate] = useState(localDate())
  const [article, setArticle] = useState(null), [comparison, setComparison] = useState(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { explorerLaws().then(rows => { setLaws(rows); setLawId(rows[0]?.law_id || '') }).catch(err => setError(err.message)) }, [])
  const perform = async task => { setBusy(true); setError(''); try { await task() } catch (err) { setError(err.message) } finally { setBusy(false) } }
  const lookup = event => { event.preventDefault(); perform(async () => { setComparison(null); setArticle(await explorerArticle({ law_id: lawId, as_of: asOf, article_no: articleNo.trim() })) }) }
  const compare = () => perform(async () => { setArticle(null); setComparison(await explorerCompare({ law_id: lawId, left_date: leftDate, right_date: rightDate, article_no: articleNo.trim() })) })
  return <main className="workspace-page law-explorer-page"><header className="page-header"><div><p className="eyebrow">LAW HISTORY</p><h1>법령 탐색·개정 비교</h1>
    <p className="small muted">보존된 공식 법령 버전의 특정 조문을 읽고 날짜별 문구를 비교합니다.</p></div></header>
    <div className="page-scroll"><Notice>{error}</Notice><form className="explorer-form" onSubmit={lookup}>
      <label>법령<select value={lawId} onChange={e => { setLawId(e.target.value); setArticle(null); setComparison(null) }}>{laws.map(law => <option value={law.law_id} key={law.law_id}>{law.name}</option>)}</select></label>
      <label>조문 번호<input value={articleNo} required onChange={e => setArticleNo(e.target.value)} placeholder="제59조의4" /></label>
      <label>조회 기준일<input type="date" value={asOf} max={localDate()} onChange={e => setAsOf(e.target.value)} required /></label>
      <button className="button" disabled={busy || !lawId}>조문 원문 조회</button>
    </form>
    <section className="explorer-compare-controls"><h2>두 날짜의 조문 비교</h2><div><label>이전 기준일<input type="date" value={leftDate} max={localDate()} onChange={e => setLeftDate(e.target.value)} /></label>
      <label>이후 기준일<input type="date" value={rightDate} max={localDate()} onChange={e => setRightDate(e.target.value)} /></label>
      <button className="button secondary" disabled={busy || !lawId || !articleNo.trim()} onClick={compare}>개정 전후 비교</button></div></section>
    {article && <article className="explorer-result"><h2>{article.version.law_name} {article.article.article_no}</h2>
      <p className="small muted">공포 {article.version.promulgation_date || '정보 없음'} · 시행 {article.version.effective_date} · 버전 {article.version.id}</p>
      <a href={article.version.source_url} target="_blank" rel="noopener noreferrer">공식 원문 보기 ↗</a>
      <pre>{article.article.content}</pre><h3>검수된 명시적 인용 관계</h3>
      {article.graph_status === 'unavailable' && <p className="small muted">관계 정보를 불러오지 못했습니다.</p>}
      {article.relations.length ? article.relations.map((relation, index) => <p key={index} className="explorer-relation">“{relation.quote}” → {relation.target_law} {relation.target_reference}</p>)
        : <p className="small muted">표시할 검수 완료 인용 관계가 없습니다.</p>}
    </article>}
    {comparison && <section className="explorer-result"><h2>조문 비교 · {articleNo}</h2>
      <p className="small muted">기준일에 해당하는 버전을 비교합니다. 실제 사건에 적용되는 법령·부칙은 따로 확인하세요.</p>
      <div className="explorer-sides">{[['이전',comparison.left],['이후',comparison.right]].map(([title,item]) => <article key={title}>
        <h3>{title} · 시행 {item.version.effective_date}</h3><a href={item.version.source_url} target="_blank" rel="noopener noreferrer">공식 원문 ↗</a><pre>{item.article.content}</pre></article>)}</div>
      <h3>변경된 줄</h3>{comparison.diff.length ? <pre className="explorer-diff">{comparison.diff.join('\n')}</pre> : <p>두 버전의 이 조문 문구가 같습니다.</p>}
      {comparison.truncated && <p className="small muted">비교 결과가 길어 일부만 표시했습니다. 양쪽 원문을 확인하세요.</p>}
    </section>}
    </div></main>
}

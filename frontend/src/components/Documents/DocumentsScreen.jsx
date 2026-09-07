import { useRef, useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import { errorMessage } from '../../api/http'
export default function DocumentsScreen({ library, onAsk }) {
  const input = useRef(), [error, setError] = useState(''), [deleting, setDeleting] = useState(null)
  const remove = async filename => {
    if (!window.confirm(`“${filename}”의 저장된 내용과 검색 데이터를 삭제할까요? 원본 PDF는 복구할 수 없으므로 재업로드가 필요합니다.`)) return
    setDeleting(filename); setError('')
    try { await library.remove(filename) } catch (e) { setError(errorMessage(e)) } finally { setDeleting(null) }
  }
  return <main className="workspace-page">
    <header className="page-header"><div><p className="eyebrow">DOCUMENT LIBRARY</p><h1>내 문서</h1></div><button className="button secondary" onClick={library.refresh} disabled={library.loading}><Icon name="refresh" size={17} />새로고침</button></header>
    <div className="page-scroll"><div className="document-upload">
      <Icon name="file" size={32} /><div><h2>문서를 더해 상담의 맥락을 넓히세요.</h2><p className="muted">텍스트 PDF만 지원합니다. 스캔 문서는 현재 지원하지 않습니다.</p><p className="small muted">같은 이름의 파일은 기존 내용을 교체합니다. 현재 로그인 사용자의 문서만 조회합니다.</p></div>
      <input hidden type="file" accept=".pdf" ref={input} onChange={e => { library.add(e.target.files?.[0]); e.target.value = '' }} /><button className="button" disabled={library.upload?.status === 'loading'} onClick={() => input.current.click()}><Icon name="plus" size={18} />PDF 업로드</button>
    </div>
    {library.upload && <Notice tone={library.upload.status === 'error' ? 'error' : 'info'}>{library.upload.message}</Notice>}
    <Notice onRetry={library.refresh}>{library.error}</Notice><Notice>{error}</Notice>
    <div className="section-heading"><h2>저장된 문서</h2><span className="muted">{library.documents.length}개</span></div>
    {library.loading && <p role="status">문서 목록을 불러오고 있습니다…</p>}
    {!library.loading && !library.error && !library.documents.length && <div className="empty-state"><Icon name="file" size={32} /><h3>아직 저장된 문서가 없습니다.</h3><p>PDF 업로드가 완료되면 이곳에서 확인할 수 있습니다.</p></div>}
    <div className="document-list">{library.documents.map(d => <article className="document-row" key={d.filename + d.category}><Icon name="file" size={25} /><div className="document-info"><h3>{d.filename}</h3><p>{d.category || '분류 없음'} · {d.law_name || '공통'}</p><p className="small muted">저장일 {d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('ko-KR') : '정보 없음'}</p></div><span className={'document-status ' + (d.search_ready ? 'ready' : '')}>{d.search_ready === true ? '검색 준비 완료' : d.search_ready === false ? '임베딩 확인 필요' : '상태 확인 필요'}</span><div className="document-actions"><button className="button secondary" disabled={!d.search_ready} onClick={() => onAsk(`내 문서 ${d.filename}에서 주요 내용을 찾아주세요`)}>문서 질문</button><button className="icon-button" disabled={deleting !== null} aria-label={d.filename + ' 삭제'} onClick={() => remove(d.filename)}><Icon name="trash" size={18} /></button></div></article>)}</div>
    <p className="small muted">검색 준비 완료는 활성 임베딩 저장 상태를 뜻하며, 모든 질문에서 해당 문서가 검색된다는 의미는 아닙니다.</p></div>
  </main>
}

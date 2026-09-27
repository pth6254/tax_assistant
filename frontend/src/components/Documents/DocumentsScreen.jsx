import { useRef, useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import { errorMessage } from '../../api/http'
import DocumentReview from './DocumentReview'
import { originalPdfUrl } from '../../api/documentReviewApi'
import './documentUpload.css'

export default function DocumentsScreen({ library, onAsk }) {
  const input = useRef(null)
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(null)
  const [reviewing, setReviewing] = useState(null)
  const [dragging, setDragging] = useState(false)
  const uploading = library.upload?.status === 'loading'

  const remove = async filename => {
    if (!window.confirm(`“${filename}”의 원본과 검색 데이터를 삭제할까요? 삭제 후 복구할 수 없으므로 재업로드가 필요합니다.`)) return
    setDeleting(filename); setError('')
    try { await library.remove(filename) } catch (e) { setError(errorMessage(e)) } finally { setDeleting(null) }
  }

  const receiveFiles = files => {
    if (uploading) return
    if (files?.length > 1) { setError('한 번에 파일 하나씩 업로드해 주세요.'); return }
    setError('')
    if (files?.[0]) library.add(files[0])
  }

  if (reviewing) return <DocumentReview filename={reviewing} onBack={() => { setReviewing(null); library.refresh() }} />
  return <main className="workspace-page">
    <header className="page-header">
      <div><p className="eyebrow">DOCUMENT LIBRARY</p><h1>내 문서</h1></div>
      <button className="button secondary" onClick={library.refresh} disabled={library.loading}><Icon name="refresh" size={17} />새로고침</button>
    </header>
    <div className="page-scroll">
      <div className={`document-upload ${dragging ? 'is-dragging' : ''}`}
        onDragEnter={event => { event.preventDefault(); if (event.dataTransfer.types.includes('Files')) setDragging(true) }}
        onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = uploading ? 'none' : 'copy' }}
        onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }}
        onDrop={event => { event.preventDefault(); setDragging(false); receiveFiles(event.dataTransfer.files) }}>
        <Icon name="file" size={32} />
        <div className="document-upload-copy">
          <h2>문서를 더해 상담의 맥락을 넓히세요.</h2>
          <p className="muted">파일을 이곳에 끌어놓거나 버튼에서 선택하세요.</p>
          <p className="small muted">PDF(스캔 OCR 포함) · DOCX · HWPX · PPTX · HTML/HTM · 파일당 최대 50MB</p>
          <p className="small muted">새 파일은 제목·문단·표 행·페이지 등 확인 가능한 구조로 검색합니다. 구형 HWP와 오피스 문서 안의 이미지 OCR은 지원하지 않습니다.</p>
        </div>
        <input hidden type="file" accept=".pdf,.docx,.hwpx,.pptx,.html,.htm" ref={input}
          onChange={event => { receiveFiles(event.target.files); event.target.value = '' }} />
        <button className="button" disabled={uploading} onClick={() => input.current?.click()}>
          {uploading ? <span className="spinner" aria-hidden="true" /> : <Icon name="plus" size={18} />}
          {uploading ? '문서 처리 중' : '문서 업로드'}
        </button>
      </div>
      <p className="document-upload-note small muted">같은 이름으로 업로드하면 기존 원본·검색 데이터와 저장된 문서 검토값이 교체됩니다. OCR의 숫자·날짜는 원본과 대조해 주세요.</p>
      {library.upload && <Notice tone={library.upload.status === 'error' ? 'error' : 'info'}>{library.upload.message}</Notice>}
      <Notice onRetry={library.refresh}>{library.error}</Notice><Notice>{error}</Notice>
      <div className="section-heading"><h2>저장된 문서</h2><span className="muted">{library.documents.length}개</span></div>
      {library.loading && <p role="status">문서 목록을 불러오고 있습니다…</p>}
      {!library.loading && !library.error && !library.documents.length &&
        <div className="empty-state"><Icon name="file" size={32} /><h3>아직 저장된 문서가 없습니다.</h3><p>문서 업로드가 완료되면 이곳에서 확인할 수 있습니다.</p></div>}
      <div className="document-list">{library.documents.map(document =>
        <article className="document-row" key={document.filename + document.category}>
          <Icon name="file" size={25} />
          <div className="document-info">
            <h3>{document.filename}</h3>
            <p>{document.category || '분류 없음'} · {document.law_name || '공통'} · {(document.format || document.filename.split('.').pop()).toUpperCase()}{document.ocr_pages ? ` · OCR ${document.ocr_pages}쪽` : ''}</p>
            <p className="small muted">{document.chunk_count ?? 0}개 검색 청크 · 저장일 {document.uploaded_at ? new Date(document.uploaded_at).toLocaleDateString('ko-KR') : '정보 없음'}</p>
            {document.chunking_version >= 2
              ? <p className="document-chunking structured">구조화 검색 · 확인된 위치를 근거에 표시</p>
              : <p className="document-chunking legacy">기존 청킹 · 구조화 검색을 적용하려면 같은 파일을 재업로드하세요</p>}
          </div>
          <span className={'document-status ' + (document.search_ready ? 'ready' : '')}>{document.search_ready === true ? '검색 준비 완료' : document.search_ready === false ? '임베딩 확인 필요' : '상태 확인 필요'}</span>
          <div className="document-actions">
            {document.filename.toLowerCase().endsWith('.pdf')
              ? <button className="button secondary" disabled={!document.original_available} onClick={() => setReviewing(document.filename)}>{document.original_available ? '원본 검토' : '재업로드 필요'}</button>
              : document.original_available
                ? <a className="button secondary" href={originalPdfUrl(document.filename)} download>원본 다운로드</a>
                : <span className="small muted">원본 없음</span>}
            <button className="button secondary" disabled={!document.search_ready} onClick={() => onAsk(`내 문서 ${document.filename}에서 주요 내용을 찾아주세요`)}>문서 질문</button>
            <button className="icon-button" disabled={deleting !== null} aria-label={document.filename + ' 삭제'} onClick={() => remove(document.filename)}><Icon name="trash" size={18} /></button>
          </div>
        </article>)}</div>
      <p className="small muted">검색 준비 완료는 활성 임베딩 저장 상태를 뜻하며, 모든 질문에서 해당 문서가 검색된다는 의미는 아닙니다.</p>
    </div>
  </main>
}

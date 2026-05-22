import { useState, useRef } from 'react'
import { uploadFile } from '../../api/uploadApi'

export default function FileUpload({ onUploaded }) {
  const [status, setStatus] = useState({ text: '', cls: '' })
  const [dragover, setDragover] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef()

  const processFiles = async (files) => {
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setStatus({ text: 'PDF 파일만 가능합니다.', cls: 'err' }); continue
      }
      setUploading(true)
      setStatus({ text: `업로드 중…`, cls: '' })
      try {
        const data = await uploadFile(file)
        setStatus({ text: `${file.name} (${data.chunks_stored}청크)`, cls: 'ok' })
        onUploaded({ name: file.name, lawName: data.law_name })
      } catch (err) {
        setStatus({ text: err.detail || '업로드 실패', cls: 'err' })
      } finally {
        setUploading(false)
      }
    }
  }

  return (
    <div>
      <div
        onClick={() => inputRef.current.click()}
        onDragOver={e => { e.preventDefault(); setDragover(true) }}
        onDragLeave={() => setDragover(false)}
        onDrop={e => { e.preventDefault(); setDragover(false); processFiles(e.dataTransfer.files) }}
        style={{
          border: `1.5px dashed ${dragover ? 'var(--accent)' : 'rgba(255,255,255,.12)'}`,
          background: dragover
            ? 'rgba(79,124,255,.08)'
            : uploading ? 'rgba(79,124,255,.04)' : 'transparent',
          borderRadius: 10,
          padding: '16px 12px',
          textAlign: 'center',
          cursor: uploading ? 'wait' : 'pointer',
          transition: 'border-color .2s, background .2s',
        }}
      >
        <input ref={inputRef} type="file" accept=".pdf" multiple style={{ display: 'none' }}
          onChange={e => { processFiles(e.target.files); e.target.value = '' }} />
        <div style={{ fontSize: 22, marginBottom: 6, opacity: dragover ? .8 : .4 }}>
          {uploading ? '⏳' : '📄'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {uploading
            ? <span style={{ color: 'var(--accent2)' }}>업로드 중…</span>
            : dragover
              ? <span style={{ color: 'var(--accent2)' }}>여기에 놓으세요</span>
              : <>PDF 드래그 또는 <span style={{ color: 'var(--accent2)' }}>클릭</span></>
          }
        </div>
      </div>
      {status.text && (
        <div style={{
          fontSize: 11, marginTop: 6,
          display: 'flex', alignItems: 'center', gap: 5,
          color: status.cls === 'ok' ? 'var(--success)' : status.cls === 'err' ? 'var(--danger)' : 'var(--text-muted)',
          padding: '5px 8px', borderRadius: 6,
          background: status.cls === 'ok' ? 'rgba(76,175,125,.08)' : status.cls === 'err' ? 'rgba(255,92,92,.08)' : 'transparent',
        }}>
          <span>{status.cls === 'ok' ? '✓' : status.cls === 'err' ? '✕' : '•'}</span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{status.text}</span>
        </div>
      )}
    </div>
  )
}

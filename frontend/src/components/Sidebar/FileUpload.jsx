import { useState, useRef } from 'react'
import { uploadFile } from '../../api/uploadApi'

export default function FileUpload({ onUploaded }) {
  const [status, setStatus] = useState({ text: '', cls: '' })
  const [dragover, setDragover] = useState(false)
  const inputRef = useRef()

  const processFiles = async (files) => {
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setStatus({ text: 'PDF 파일만 가능합니다.', cls: 'err' }); continue
      }
      setStatus({ text: `${file.name} 업로드 중…`, cls: '' })
      try {
        const data = await uploadFile(file)
        setStatus({ text: `✓ ${file.name} (${data.chunks_stored}청크)`, cls: 'ok' })
        onUploaded({ name: file.name, lawName: data.law_name })
      } catch (err) {
        setStatus({ text: err.detail || '업로드 실패', cls: 'err' })
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
          border: `1.5px dashed ${dragover ? 'var(--accent)' : 'var(--border)'}`,
          background: dragover ? 'rgba(79,124,255,.05)' : 'transparent',
          borderRadius: 'var(--radius)',
          padding: '22px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'border-color .2s, background .2s',
        }}
      >
        <input ref={inputRef} type="file" accept=".pdf" multiple style={{ display: 'none' }}
          onChange={e => { processFiles(e.target.files); e.target.value = '' }} />
        <div style={{ fontSize: 28, marginBottom: 8, opacity: .5 }}>📄</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          PDF를 여기에 드래그하거나<br />클릭해서 선택하세요
        </div>
      </div>
      {status.text && (
        <div style={{
          fontSize: 12, textAlign: 'center', marginTop: 8,
          color: status.cls === 'ok' ? 'var(--success)' : status.cls === 'err' ? 'var(--danger)' : 'var(--text-muted)'
        }}>{status.text}</div>
      )}
    </div>
  )
}

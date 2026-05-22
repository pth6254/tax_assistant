import { useRef, useState } from 'react'
import { uploadFile } from '../../api/uploadApi'

export default function ChatInput({ onSend, disabled }) {
  const textRef = useRef()
  const fileRef = useRef()
  const [focused,     setFocused]     = useState(false)
  const [uploadState, setUploadState] = useState(null) // null | 'loading' | 'ok' | 'err'
  const [uploadMsg,   setUploadMsg]   = useState('')

  // ── 텍스트 전송 ───────────────────────────────────────────────
  const handleKeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const submit = () => {
    const val = textRef.current.value.trim()
    if (!val || disabled) return
    onSend(val)
    textRef.current.value = ''
    textRef.current.style.height = 'auto'
  }

  const autoResize = (e) => {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
  }

  // ── 파일 첨부 ────────────────────────────────────────────────
  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadState('err')
      setUploadMsg('PDF 파일만 첨부할 수 있습니다.')
      setTimeout(() => setUploadState(null), 3000)
      return
    }

    setUploadState('loading')
    setUploadMsg(file.name)
    try {
      const data = await uploadFile(file)
      setUploadState('ok')
      setUploadMsg(`${file.name} (${data.chunks_stored}청크 저장됨)`)
      setTimeout(() => setUploadState(null), 4000)
    } catch (err) {
      setUploadState('err')
      setUploadMsg(err.detail || '업로드에 실패했습니다.')
      setTimeout(() => setUploadState(null), 4000)
    }
  }

  const stateColor = { loading: 'var(--text-muted)', ok: 'var(--success)', err: 'var(--danger)' }
  const stateBg    = { loading: 'rgba(255,255,255,.04)', ok: 'rgba(76,175,125,.08)', err: 'rgba(255,92,92,.08)' }
  const stateIcon  = {
    loading: <span style={{ width:11, height:11, flexShrink:0, border:'1.5px solid rgba(255,255,255,.2)', borderTopColor:'var(--text-muted)', borderRadius:'50%', animation:'spin .7s linear infinite', display:'inline-block' }} />,
    ok:  '✓',
    err: '✕',
  }

  return (
    <div style={{ padding: '12px 28px 22px' }}>
      {/* 업로드 상태 */}
      {uploadState && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 7,
          fontSize: 12,
          color: stateColor[uploadState],
          background: stateBg[uploadState],
          border: `1px solid ${stateColor[uploadState]}30`,
          borderRadius: 8, padding: '6px 12px', marginBottom: 8,
          animation: 'slideUp .2s ease',
        }}>
          {stateIcon[uploadState]}
          <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {uploadMsg}
          </span>
        </div>
      )}

      {/* 입력 컨테이너 */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'flex-end',
        background: 'var(--surface)',
        border: `1px solid ${focused ? 'rgba(79,124,255,.5)' : 'var(--border)'}`,
        borderRadius: 16,
        padding: '6px 6px 6px 8px',
        boxShadow: focused ? '0 0 0 3px rgba(79,124,255,.1)' : 'none',
        transition: 'border-color .2s, box-shadow .2s',
      }}>
        {/* 파일 첨부 버튼 */}
        <input ref={fileRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={handleFileChange} />
        <button
          onClick={() => fileRef.current.click()}
          disabled={uploadState === 'loading'}
          title="PDF 파일 첨부"
          style={{
            width: 36, height: 36, flexShrink: 0, alignSelf: 'flex-end', marginBottom: 2,
            background: 'transparent',
            border: '1px solid var(--border)',
            borderRadius: 10,
            color: uploadState === 'loading' ? 'var(--accent2)' : 'var(--text-muted)',
            cursor: uploadState === 'loading' ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'border-color .15s, color .15s, background .15s',
          }}
          onMouseEnter={e => {
            if (uploadState !== 'loading') {
              e.currentTarget.style.borderColor = 'rgba(79,124,255,.5)'
              e.currentTarget.style.color = 'var(--accent2)'
              e.currentTarget.style.background = 'rgba(79,124,255,.08)'
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.background = 'transparent'
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        {/* 텍스트 입력 */}
        <textarea
          ref={textRef}
          placeholder="세무 관련 질문을 입력하세요…"
          rows={1}
          onKeyDown={handleKeydown}
          onInput={autoResize}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            padding: '10px 4px', color: 'var(--text)',
            fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.5,
            resize: 'none', minHeight: 42, maxHeight: 200,
          }}
        />

        {/* 전송 버튼 */}
        <button
          onClick={submit}
          disabled={disabled}
          style={{
            width: 44, height: 44, flexShrink: 0, alignSelf: 'flex-end',
            background: disabled ? 'rgba(79,124,255,.3)' : 'var(--accent)',
            border: 'none', borderRadius: 12, color: '#fff',
            cursor: disabled ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background .15s, transform .1s',
            boxShadow: disabled ? 'none' : '0 2px 8px rgba(79,124,255,.35)',
          }}
          onMouseEnter={e => { if (!disabled) e.currentTarget.style.transform = 'scale(1.05)' }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5" /><polyline points="5 12 12 5 19 12" />
          </svg>
        </button>
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8, opacity: .5 }}>
        Enter로 전송 · Shift+Enter로 줄바꿈 · + 버튼으로 PDF 첨부
      </div>
    </div>
  )
}

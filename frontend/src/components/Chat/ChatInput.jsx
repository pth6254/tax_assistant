import { useRef, useState } from 'react'

export default function ChatInput({ onSend, disabled }) {
  const ref = useRef()
  const [focused, setFocused] = useState(false)

  const handleKeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const submit = () => {
    const val = ref.current.value.trim()
    if (!val || disabled) return
    onSend(val)
    ref.current.value = ''
    ref.current.style.height = 'auto'
  }

  const autoResize = (e) => {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
  }

  return (
    <div style={{
      padding: '16px 28px 24px',
      borderTop: '1px solid var(--border)',
    }}>
      <div style={{
        display: 'flex', gap: 10, alignItems: 'flex-end',
        background: 'var(--surface)',
        border: `1px solid ${focused ? 'rgba(79,124,255,.5)' : 'var(--border)'}`,
        borderRadius: 16,
        padding: '6px 6px 6px 18px',
        boxShadow: focused ? '0 0 0 3px rgba(79,124,255,.1)' : 'none',
        transition: 'border-color .2s, box-shadow .2s',
      }}>
        <textarea
          ref={ref}
          placeholder="세무 관련 질문을 입력하세요…"
          rows={1}
          onKeyDown={handleKeydown}
          onInput={autoResize}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            padding: '10px 0',
            color: 'var(--text)',
            fontFamily: 'var(--font-body)',
            fontSize: 14, lineHeight: 1.5,
            resize: 'none', minHeight: 42, maxHeight: 200,
          }}
        />
        <button
          onClick={submit}
          disabled={disabled}
          style={{
            width: 44, height: 44,
            background: disabled ? 'rgba(79,124,255,.3)' : 'var(--accent)',
            border: 'none', borderRadius: 12,
            color: '#fff', cursor: disabled ? 'not-allowed' : 'pointer',
            flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background .15s, transform .1s',
            boxShadow: disabled ? 'none' : '0 2px 8px rgba(79,124,255,.35)',
          }}
          onMouseEnter={e => { if (!disabled) e.currentTarget.style.transform = 'scale(1.05)' }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5" />
            <polyline points="5 12 12 5 19 12" />
          </svg>
        </button>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8, opacity: .6 }}>
        Enter로 전송 · Shift+Enter로 줄바꿈
      </div>
    </div>
  )
}

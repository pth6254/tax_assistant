import { useRef } from 'react'

export default function ChatInput({ onSend, disabled }) {
  const ref = useRef()

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
      padding: '20px 32px 28px',
      borderTop: '1px solid var(--border)',
      display: 'flex', gap: 12, alignItems: 'flex-end',
    }}>
      <textarea
        ref={ref}
        placeholder="세무 관련 질문을 입력하세요…"
        rows={1}
        onKeyDown={handleKeydown}
        onInput={autoResize}
        style={{
          flex: 1,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          padding: '14px 18px',
          color: 'var(--text)',
          fontFamily: 'var(--font-body)',
          fontSize: 14, lineHeight: 1.5,
          resize: 'none', minHeight: 52, maxHeight: 200,
          outline: 'none',
        }}
      />
      <button
        onClick={submit}
        disabled={disabled}
        style={{
          width: 52, height: 52,
          background: 'var(--accent)',
          border: 'none', borderRadius: 14,
          color: '#fff', fontSize: 20,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.35 : 1,
          flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        ↑
      </button>
    </div>
  )
}

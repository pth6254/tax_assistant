import { useEffect, useRef } from 'react'
import { marked } from 'marked'

export default function MessageBubble({ message, userInitial }) {
  const isUser = message.role === 'user'
  const bubbleRef = useRef()

  useEffect(() => {
    if (!isUser && bubbleRef.current) {
      bubbleRef.current.innerHTML = marked.parse(message.content)
    }
  }, [message.content, isUser])

  return (
    <div style={{
      display: 'flex',
      gap: 14,
      flexDirection: isUser ? 'row-reverse' : 'row',
      animation: 'slideUp .3s ease',
    }}>
      {/* 아바타 */}
      <div style={{
        width: 34, height: 34, borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, flexShrink: 0, marginTop: 2,
        ...(isUser
          ? { background: 'var(--surface2)', border: '1px solid var(--border)' }
          : { background: 'linear-gradient(135deg, var(--accent), #7c4fff)', color: '#fff' }
        )
      }}>
        {isUser ? userInitial : '⚖'}
      </div>

      {/* 말풍선 */}
      <div
        ref={isUser ? undefined : bubbleRef}
        className={isUser ? undefined : 'markdown-bubble'}
        style={{
          maxWidth: '68%', padding: '14px 18px',
          fontSize: 14, lineHeight: 1.75,
          ...(isUser
            ? {
                background: 'var(--accent)', color: '#fff',
                borderRadius: '16px 4px 16px 16px',
              }
            : {
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: '4px 16px 16px 16px',
              }
          )
        }}
      >
        {isUser && message.content.replace(/</g, '&lt;')}
      </div>
    </div>
  )
}

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
      gap: 12,
      flexDirection: isUser ? 'row-reverse' : 'row',
      animation: 'slideUp .25s ease',
    }}>
      {/* 아바타 */}
      <div style={{
        width: 34, height: 34, borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 13, flexShrink: 0, marginTop: 2,
        fontWeight: 600,
        ...(isUser
          ? {
              background: 'var(--surface2)',
              border: '1px solid rgba(255,255,255,.1)',
              color: 'var(--text-muted)',
            }
          : {
              background: 'linear-gradient(135deg, var(--accent) 0%, #7c4fff 100%)',
              color: '#fff',
              boxShadow: '0 3px 10px rgba(79,124,255,.3)',
            }
        )
      }}>
        {isUser ? userInitial : '⚖'}
      </div>

      {/* 말풍선 */}
      <div
        ref={isUser ? undefined : bubbleRef}
        className={isUser ? undefined : 'markdown-bubble'}
        style={{
          maxWidth: '70%', padding: '13px 17px',
          fontSize: 14, lineHeight: 1.75,
          ...(isUser
            ? {
                background: 'linear-gradient(135deg, var(--accent) 0%, rgba(79,124,255,.85) 100%)',
                color: '#fff',
                borderRadius: '16px 4px 16px 16px',
                boxShadow: '0 2px 12px rgba(79,124,255,.25)',
              }
            : {
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderLeft: '3px solid rgba(79,124,255,.35)',
                borderRadius: '4px 16px 16px 16px',
              }
          )
        }}
      >
        {isUser && message.content}
      </div>
    </div>
  )
}

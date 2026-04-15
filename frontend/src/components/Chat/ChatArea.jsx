import { useEffect, useRef } from 'react'
import { useChat } from '../../hooks/useChat'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

function TypingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 14, animation: 'slideUp .3s ease' }}>
      <div style={{
        width: 34, height: 34, borderRadius: '50%',
        background: 'linear-gradient(135deg, var(--accent), #7c4fff)',
        color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, flexShrink: 0,
      }}>⚖</div>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: '4px 16px 16px 16px',
        padding: '14px 18px',
      }}>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          {[0, 0.2, 0.4].map((delay, i) => (
            <span key={i} style={{
              width: 7, height: 7, background: 'var(--text-muted)',
              borderRadius: '50%',
              animation: `blink 1.2s infinite ${delay}s`,
              display: 'inline-block',
            }} />
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ChatArea({ user }) {
  const { messages, loading, sendMessage } = useChat(user.id)
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <main style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      background: 'var(--bg)', minWidth: 0,
    }}>
      {/* 헤더 */}
      <header style={{
        padding: '20px 32px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'var(--success)',
          boxShadow: '0 0 0 3px rgba(76,175,125,.2)',
        }} />
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 400, letterSpacing: '-0.3px' }}>
          세무 법령 RAG 어시스턴트
        </h1>
      </header>

      {/* 메시지 목록 */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: 32,
        display: 'flex', flexDirection: 'column', gap: 24,
      }}>
        {messages.length === 0 && (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: 16, color: 'var(--text-muted)',
            textAlign: 'center', padding: 40, margin: 'auto',
          }}>
            <div style={{ fontSize: 48, opacity: .3 }}>⚖️</div>
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--text)', fontWeight: 400 }}>
              무엇이든 물어보세요
            </div>
            <div style={{ fontSize: 14, lineHeight: 1.6, maxWidth: 360 }}>
              업로드한 세무 법령 문서를 기반으로<br />정확한 법적 근거와 함께 답변드립니다.
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            message={msg}
            userInitial={(user.email[0] || 'U').toUpperCase()}
          />
        ))}

        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={sendMessage} disabled={loading} />
    </main>
  )
}

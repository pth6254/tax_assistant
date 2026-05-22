import { useEffect, useRef } from 'react'
import { useChat } from '../../hooks/useChat'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

const QUICK_QUESTIONS = [
  '양도소득세 계산 방법을 알려주세요',
  '1세대 1주택 비과세 요건이 무엇인가요?',
  '증여세 공제 한도가 얼마인가요?',
]

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
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderLeft: '3px solid rgba(79,124,255,.4)',
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

export default function ChatArea({ user, conversationId, conversationTitle, onMessageSent }) {
  const { messages, loading, sendMessage } = useChat(conversationId)
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSend = (query) => {
    sendMessage(query, onMessageSent)
  }

  if (!conversationId) {
    return (
      <main style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: 'var(--bg)', alignItems: 'center', justifyContent: 'center',
        gap: 16, color: 'var(--text-muted)', textAlign: 'center',
      }}>
        <div style={{ fontSize: 48, opacity: .2 }}>⚖️</div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--text)' }}>
          대화를 선택하거나 새 대화를 시작하세요
        </div>
        <div style={{ fontSize: 13 }}>좌측 사이드바의 + 버튼을 눌러주세요.</div>
      </main>
    )
  }

  return (
    <main style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      background: 'var(--bg)', minWidth: 0,
    }}>
      {/* 헤더 */}
      <header style={{
        padding: '18px 32px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
        background: 'rgba(24,28,39,.8)',
        backdropFilter: 'blur(8px)',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'var(--success)',
          animation: 'pulse 2.5s infinite',
        }} />
        <h1 style={{
          fontFamily: 'var(--font-serif)', fontSize: 17,
          fontWeight: 400, letterSpacing: '-0.3px',
          flex: 1,
        }}>
          {conversationTitle || '새 대화'}
        </h1>
      </header>

      {/* 메시지 목록 */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '28px 32px',
        display: 'flex', flexDirection: 'column', gap: 20,
      }}>
        {messages.length === 0 && !loading && (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: 20, color: 'var(--text-muted)',
            textAlign: 'center', padding: 40, margin: 'auto',
          }}>
            <div style={{
              width: 72, height: 72, borderRadius: 20,
              background: 'linear-gradient(135deg, rgba(79,124,255,.15), rgba(124,79,255,.15))',
              border: '1px solid rgba(79,124,255,.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 34,
            }}>
              ⚖️
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--text)', fontWeight: 400, marginBottom: 8 }}>
                무엇이든 물어보세요
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.7, maxWidth: 340 }}>
                세무 법령 문서를 기반으로<br />정확한 법적 근거와 함께 답변드립니다.
              </div>
            </div>
            {/* 빠른 질문 칩 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 420 }}>
              {QUICK_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(q)}
                  style={{
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 10,
                    padding: '10px 16px',
                    color: 'var(--text)',
                    fontSize: 13, cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                    transition: 'border-color .15s, background .15s',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = 'rgba(79,124,255,.4)'
                    e.currentTarget.style.background = 'rgba(79,124,255,.06)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.background = 'var(--surface)'
                  }}
                >
                  <span>{q}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 16, flexShrink: 0 }}>→</span>
                </button>
              ))}
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

      <ChatInput onSend={handleSend} disabled={loading} />
    </main>
  )
}

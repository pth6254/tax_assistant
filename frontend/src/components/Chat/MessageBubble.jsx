import { useEffect, useRef } from 'react'
import { marked } from 'marked'

// _COMBINED_PROMPT의 "근거 출처 목록" 형식과 동일한 패턴 — [법률] 법령명 제N조
// 조문번호는 공백 변형 허용 (모델이 "제 50 조"처럼 출력하는 경우가 많음, citation_guard.py와 동일)
const CITATION_RE = /\[(법률|시행령|시행규칙)\]\s*([^\n[]+?)\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)/g

function linkifyCitations(content) {
  return content.replace(CITATION_RE, (match, label, lawName, articleNo) => {
    const law = lawName.trim().replace(/"/g, '&quot;')
    const article = articleNo.replace(/\s+/g, '')  // DB 조회용 표준형('제50조')으로 정규화
    return `<span class="citation-link" data-law="${law}" data-article="${article}">${match}</span>`
  })
}

const CALC_TAB_LABELS = {
  income_tax:    { icon: '💼', label: '소득세' },
  capital_gains: { icon: '🏠', label: '양도소득세' },
  inheritance:   { icon: '📜', label: '상속세' },
  gift:          { icon: '🎁', label: '증여세' },
}

export default function MessageBubble({ message, userInitial, onCitationClick, onOpenCalculator }) {
  const isUser = message.role === 'user'
  const bubbleRef = useRef()

  useEffect(() => {
    if (!isUser && bubbleRef.current) {
      bubbleRef.current.innerHTML = marked.parse(linkifyCitations(message.content))
    }
  }, [message.content, isUser])

  useEffect(() => {
    if (isUser || !bubbleRef.current || !onCitationClick) return
    const el = bubbleRef.current
    const handleClick = (e) => {
      const target = e.target.closest('.citation-link')
      if (!target) return
      onCitationClick(target.dataset.law, target.dataset.article)
    }
    el.addEventListener('click', handleClick)
    return () => el.removeEventListener('click', handleClick)
  }, [isUser, onCitationClick])

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

      {/* 말풍선 + 계산기 연결 버튼 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: '70%', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        <div
          ref={isUser ? undefined : bubbleRef}
          className={isUser ? undefined : 'markdown-bubble'}
          style={{
            padding: '13px 17px',
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

        {!isUser && message.calc && onOpenCalculator && (
          <button
            onClick={() => onOpenCalculator(message.calc.tool, message.calc.params)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'rgba(79,124,255,.08)',
              border: '1px solid rgba(79,124,255,.25)',
              borderRadius: 9, padding: '7px 13px',
              color: 'var(--accent2)', fontSize: 12.5, cursor: 'pointer',
              transition: 'background .15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(79,124,255,.16)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(79,124,255,.08)' }}
          >
            <span>{CALC_TAB_LABELS[message.calc.tool]?.icon ?? '🧮'}</span>
            계산기 화면에서 {CALC_TAB_LABELS[message.calc.tool]?.label ?? ''} 조건 바꿔보기 →
          </button>
        )}
      </div>
    </div>
  )
}

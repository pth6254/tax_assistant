import { useState } from 'react'
import FileUpload from './FileUpload'

const NAV_ITEMS = [
  { key: 'chat',       label: '채팅',     icon: '💬' },
  { key: 'calculator', label: '세금계산기', icon: '🧮' },
  { key: 'profile',    label: '내 정보',   icon: '👤' },
]

function relativeTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const min  = diff / 60_000
  if (min < 1)   return '방금'
  if (min < 60)  return `${Math.floor(min)}분 전`
  const h = min / 60
  if (h < 24)    return `${Math.floor(h)}시간 전`
  const d = h / 24
  if (d < 7)     return `${Math.floor(d)}일 전`
  return new Date(dateStr).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

function ConvItem({ conv, active, onSelect, onDelete }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '9px 10px',
        borderRadius: 8,
        background: active
          ? 'rgba(79,124,255,.18)'
          : hovered ? 'var(--surface2)' : 'transparent',
        border: active ? '1px solid rgba(79,124,255,.3)' : '1px solid transparent',
        cursor: 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 6,
        transition: 'background .12s',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13,
          color: active ? 'var(--accent2)' : 'var(--text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {conv.title}
        </div>
        <div style={{
          fontSize: 11, color: 'var(--text-muted)', marginTop: 2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {conv.preview || relativeTime(conv.updated_at)}
        </div>
      </div>
      {hovered && (
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          style={{
            background: 'none', border: 'none',
            color: 'var(--text-muted)', cursor: 'pointer',
            fontSize: 16, lineHeight: 1, padding: '0 2px',
            flexShrink: 0, marginTop: 1,
          }}
          title="대화 삭제"
        >
          ×
        </button>
      )}
    </div>
  )
}

export default function Sidebar({
  user, onLogout,
  view, onViewChange,
  conversations, currentConversationId,
  onSelectConversation, onCreateConversation, onDeleteConversation,
}) {
  const [files, setFiles] = useState([])

  return (
    <aside style={{
      width: 280, flexShrink: 0,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* 로고 */}
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 18,
        padding: '20px 24px 16px',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        세무 <span style={{ color: 'var(--accent2)' }}>AI</span>
      </div>

      {/* 네비게이션 */}
      <div style={{ padding: '10px 12px', display: 'flex', gap: 5, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        {NAV_ITEMS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => onViewChange(key)}
            style={{
              flex: 1,
              background: view === key ? 'var(--accent)' : 'var(--surface2)',
              border: '1px solid ' + (view === key ? 'var(--accent)' : 'var(--border)'),
              borderRadius: 8,
              padding: '7px 2px',
              color: view === key ? '#fff' : 'var(--text-muted)',
              fontSize: 10,
              cursor: 'pointer',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              transition: 'all .15s',
            }}
          >
            <span style={{ fontSize: 14 }}>{icon}</span>
            {label}
          </button>
        ))}
      </div>

      {/* 중간 영역 */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {view === 'chat' ? (
          <>
            {/* 새 대화 버튼 */}
            <div style={{ padding: '10px 12px 6px', flexShrink: 0 }}>
              <button
                onClick={onCreateConversation}
                style={{
                  width: '100%',
                  background: 'var(--surface2)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  color: 'var(--text-muted)',
                  fontSize: 12, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  transition: 'border-color .15s, color .15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent2)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
                새 대화
              </button>
            </div>

            {/* 대화 목록 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
              {conversations.length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0' }}>
                  대화 내역이 없습니다.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {conversations.map(conv => (
                    <ConvItem
                      key={conv.id}
                      conv={conv}
                      active={conv.id === currentConversationId}
                      onSelect={() => onSelectConversation(conv.id)}
                      onDelete={() => onDeleteConversation(conv.id)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* 문서 업로드 (채팅 뷰에서만) */}
            <div style={{
              padding: '10px 16px',
              borderTop: '1px solid var(--border)',
              flexShrink: 0,
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
                문서 업로드
              </div>
              <FileUpload onUploaded={f => setFiles(prev => [...prev, f])} />
              {files.slice(-2).map((f, i) => (
                <div key={i} style={{
                  marginTop: 6, fontSize: 11, color: 'var(--text-muted)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  ✓ {f.name}
                </div>
              ))}
            </div>
          </>
        ) : (
          <div style={{ flex: 1 }} />
        )}
      </div>

      {/* 사용자 정보 */}
      <div style={{
        padding: '14px 20px',
        borderTop: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 10,
        flexShrink: 0,
      }}>
        <div style={{
          width: 30, height: 30,
          background: 'var(--accent)',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, color: '#fff', fontWeight: 500, flexShrink: 0,
        }}>
          {(user.email[0] || '?').toUpperCase()}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {user.email}
        </div>
        <button onClick={onLogout} style={{
          background: 'none', border: 'none',
          color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer',
          padding: '4px 6px', borderRadius: 6,
        }}>
          로그아웃
        </button>
      </div>
    </aside>
  )
}

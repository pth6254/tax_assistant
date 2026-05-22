import { useState } from 'react'
import FileUpload from './FileUpload'

const NAV_ITEMS = [
  { key: 'chat',       label: '채팅',      icon: '💬' },
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
        borderRadius: 9,
        background: active
          ? 'rgba(79,124,255,.15)'
          : hovered ? 'rgba(255,255,255,.04)' : 'transparent',
        border: active ? '1px solid rgba(79,124,255,.28)' : '1px solid transparent',
        cursor: 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 8,
        transition: 'background .12s, border-color .12s',
      }}
    >
      <div style={{
        width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginTop: 5,
        background: active ? 'var(--accent2)' : 'transparent',
        transition: 'background .12s',
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13,
          color: active ? 'var(--accent2)' : 'var(--text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          fontWeight: active ? 500 : 400,
        }}>
          {conv.title}
        </div>
        <div style={{
          fontSize: 11, color: 'var(--text-muted)', marginTop: 2,
        }}>
          {conv.preview || relativeTime(conv.updated_at)}
        </div>
      </div>
      {hovered && (
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          style={{
            background: 'rgba(255,92,92,.12)',
            border: '1px solid rgba(255,92,92,.2)',
            borderRadius: 5,
            color: 'var(--danger)', cursor: 'pointer',
            fontSize: 13, lineHeight: 1,
            padding: '2px 6px',
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
        padding: '18px 20px 16px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{
          width: 34, height: 34, borderRadius: 9,
          background: 'linear-gradient(135deg, var(--accent), #7c4fff)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 17, flexShrink: 0,
          boxShadow: '0 4px 12px rgba(79,124,255,.3)',
        }}>
          ⚖
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, letterSpacing: '-0.3px', lineHeight: 1.2 }}>
            세무 <span style={{ color: 'var(--accent2)' }}>AI</span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>Tax Assistant</div>
        </div>
      </div>

      {/* 네비게이션 */}
      <div style={{ padding: '10px 12px', display: 'flex', gap: 5, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        {NAV_ITEMS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => onViewChange(key)}
            style={{
              flex: 1,
              background: view === key
                ? 'linear-gradient(135deg, var(--accent), rgba(79,124,255,.7))'
                : 'var(--surface2)',
              border: '1px solid ' + (view === key ? 'transparent' : 'var(--border)'),
              borderRadius: 9,
              padding: '8px 2px',
              color: view === key ? '#fff' : 'var(--text-muted)',
              fontSize: 10,
              cursor: 'pointer',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
              transition: 'all .15s',
              boxShadow: view === key ? '0 3px 10px rgba(79,124,255,.3)' : 'none',
            }}
          >
            <span style={{ fontSize: 15 }}>{icon}</span>
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
                  background: 'transparent',
                  border: '1px dashed rgba(79,124,255,.35)',
                  borderRadius: 9,
                  padding: '8px 12px',
                  color: 'var(--accent2)',
                  fontSize: 12, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  transition: 'background .15s, border-color .15s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(79,124,255,.08)'
                  e.currentTarget.style.borderColor = 'rgba(79,124,255,.6)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.borderColor = 'rgba(79,124,255,.35)'
                }}
              >
                <span style={{ fontSize: 16, lineHeight: 1, fontWeight: 300 }}>+</span>
                새 대화 시작
              </button>
            </div>

            {/* 대화 목록 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
              {conversations.length === 0 ? (
                <div style={{
                  fontSize: 12, color: 'var(--text-muted)',
                  textAlign: 'center', padding: '32px 16px',
                  lineHeight: 1.6,
                }}>
                  <div style={{ fontSize: 28, marginBottom: 8, opacity: .3 }}>💬</div>
                  아직 대화 내역이 없습니다.
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

            {/* 문서 업로드 */}
            <div style={{
              padding: '12px 14px',
              borderTop: '1px solid var(--border)',
              flexShrink: 0,
            }}>
              <div style={{
                fontSize: 10, color: 'var(--text-muted)',
                letterSpacing: '.8px', textTransform: 'uppercase',
                marginBottom: 8, fontWeight: 600,
              }}>
                📎 문서 업로드
              </div>
              <FileUpload onUploaded={f => setFiles(prev => [...prev, f])} />
              {files.slice(-2).map((f, i) => (
                <div key={i} style={{
                  marginTop: 5, fontSize: 11,
                  color: 'var(--success)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}>
                  <span>✓</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</span>
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
        padding: '12px 16px',
        borderTop: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 10,
        flexShrink: 0,
      }}>
        <div style={{
          width: 32, height: 32,
          background: 'linear-gradient(135deg, var(--accent), #7c4fff)',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, color: '#fff', fontWeight: 600, flexShrink: 0,
        }}>
          {(user.email[0] || '?').toUpperCase()}
        </div>
        <div style={{
          flex: 1, minWidth: 0,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          fontSize: 12, color: 'var(--text-muted)',
        }}>
          {user.email}
        </div>
        <button
          onClick={onLogout}
          style={{
            background: 'none', border: 'none',
            color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer',
            padding: '4px 8px', borderRadius: 6,
            transition: 'color .15s, background .15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)'; e.currentTarget.style.background = 'rgba(255,92,92,.08)' }}
          onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'none' }}
        >
          로그아웃
        </button>
      </div>
    </aside>
  )
}

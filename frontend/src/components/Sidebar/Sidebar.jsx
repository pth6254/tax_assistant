import { useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'

const NAV = [{ key: 'chat', label: '채팅', icon: 'chat' }, { key: 'documents', label: '내 문서', icon: 'file' },
  { key: 'calculator', label: '세금계산기', icon: 'calculator' }, { key: 'profile', label: '내 정보', icon: 'user' }]
export default function Sidebar({ user, onLogout, view, onViewChange, conversations, currentConversationId, onSelectConversation, onCreateConversation, onDeleteConversation, collapsed, onToggle, error, onRetry }) {
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState('')
  const perform = async action => {
    if (busy) return
    setBusy(true); setLocalError('')
    try { await action() } catch { setLocalError('작업을 완료하지 못했습니다. 다시 시도해 주세요.') } finally { setBusy(false) }
  }
  return <aside className={'sidebar ' + (collapsed ? 'is-collapsed' : '')} aria-label="탐색 메뉴">
    <div className="brand"><span className="brand-mark"><Icon name="book" /></span><strong className="sidebar-label">세무 AI<span>Tax workspace</span></strong>
      <button className="icon-button sidebar-label" aria-label="사이드바 접기" onClick={onToggle}><Icon name="menu" /></button></div>
    <nav className="main-nav">{NAV.map(n => <button key={n.key} title={n.label} aria-label={n.label} aria-current={view === n.key ? 'page' : undefined} className={view === n.key ? 'selected' : ''} onClick={() => onViewChange(n.key)}><Icon name={n.icon} /><span className="sidebar-label">{n.label}</span></button>)}</nav>
    <button className="button new-chat" disabled={busy} title="새 대화 시작" onClick={() => perform(onCreateConversation)}><Icon name="plus" /><span className="sidebar-label">새 대화 시작</span></button>
    <div className="conversation-list sidebar-label">
      <p className="section-label">최근 대화</p>
      <Notice onRetry={onRetry}>{error || localError}</Notice>
      {!conversations.length && !error && <p className="muted small">새 대화에서 질문을 시작하세요.</p>}
      {conversations.map(c => <div key={c.id} className={'conversation-item ' + (currentConversationId === c.id ? 'selected' : '')}>
        <button className="conversation-title" onClick={() => onSelectConversation(c.id)}>{c.title || '새 대화'}</button>
        <button className="icon-button" aria-label={(c.title || '새 대화') + ' 삭제'} disabled={busy} onClick={() => { if (window.confirm('이 대화를 삭제할까요? 삭제 후 복구할 수 없습니다.')) perform(() => onDeleteConversation(c.id)) }}><Icon name="trash" size={16} /></button>
      </div>)}
    </div>
    <div className="sidebar-bottom"><span className="sidebar-label user-email">{user.email}</span><button className="icon-button" title="로그아웃" aria-label="로그아웃" onClick={() => perform(onLogout)}><Icon name="logout" /></button></div>
  </aside>
}

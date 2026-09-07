import { useState, useEffect, useRef } from 'react'
import { useAuth } from './hooks/useAuth'
import { useConversations } from './hooks/useConversations'
import { useDocumentLibrary } from './hooks/useDocumentLibrary'
import AuthScreen from './components/Auth/AuthScreen'
import Sidebar from './components/Sidebar/Sidebar'
import ChatArea from './components/Chat/ChatArea'
import CalculatorScreen from './components/Calculator/CalculatorScreen'
import DocumentsScreen from './components/Documents/DocumentsScreen'
import ProfileScreen from './components/Profile/ProfileScreen'
import Icon from './components/ui/Icon'
import Notice from './components/ui/Notice'
export default function App() {
  const auth = useAuth()
  return auth.user ? <Workspace key={auth.user.id || auth.user.email} user={auth.user} onLogout={auth.logout} /> : <AuthScreen onLogin={auth.login} onSignup={auth.signup} />
}
function Workspace({ user, onLogout }) {
  const [view, setView] = useState('chat'), [collapsed, setCollapsed] = useState(() => window.innerWidth <= 1100)
  const { conversations, currentId, refresh, select, create, remove, error } = useConversations()
  const [prefill, setPrefill] = useState(null), [pendingQuestion, setPendingQuestion] = useState(null), [actionError, setActionError] = useState('')
  const creating = useRef(false)
  const library = useDocumentLibrary()
  useEffect(() => { let active = true; refresh().then(list => { if (active && list.length) select(list[0].id) }); return () => { active = false } }, [refresh, select])
  const changeView = key => { setView(key); if (window.innerWidth <= 1100) setCollapsed(true) }
  const newConversation = async query => {
    if (creating.current) return
    creating.current = true; setActionError('')
    try { await create(); if (typeof query === 'string') setPendingQuestion(query); changeView('chat') }
    catch { setActionError('대화를 만들지 못했습니다. 다시 시도해 주세요.') }
    finally { creating.current = false }
  }
  const ask = async question => {
    if (!currentId) { await newConversation(question); return }
    setPendingQuestion(question); changeView('chat')
  }
  const current = conversations.find(c => c.id === currentId)
  return <div className="app-shell">
    {!collapsed && <button className="sidebar-scrim" aria-label="메뉴 닫기" onClick={() => setCollapsed(true)} />}
    <Sidebar user={user} onLogout={onLogout} view={view} onViewChange={changeView} conversations={conversations} currentConversationId={currentId}
      onSelectConversation={id => { select(id); changeView('chat') }} onCreateConversation={() => newConversation()} onDeleteConversation={remove}
      collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} error={error} onRetry={refresh} />
    <div className="main-shell">
      <div className="workspace-toolbar"><button className="icon-button" aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'} aria-expanded={!collapsed} onClick={() => setCollapsed(c => !c)}><Icon name="menu" /></button><span>나의 세무 작업 공간</span></div>
      <Notice>{actionError}</Notice>
      <div className="view-host">
        {view === 'documents' ? <DocumentsScreen library={library} onAsk={ask} />
          : view === 'calculator' ? <CalculatorScreen initial={prefill} onInitialConsumed={() => setPrefill(null)} onAskAboutResult={ask} />
          : view === 'profile' ? <ProfileScreen onLogout={onLogout} />
          : <ChatArea user={user} conversationId={currentId} conversationTitle={current?.title} onMessageSent={refresh}
              onOpenCalculator={(tool, params) => { setPrefill({ tool, params }); changeView('calculator') }}
              pendingQuestion={pendingQuestion} onPendingQuestionConsumed={() => setPendingQuestion(null)} onCreateConversation={newConversation} library={library} />}
      </div>
    </div>
  </div>
}

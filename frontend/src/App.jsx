import { useState, useEffect } from 'react'
import { useAuth } from './hooks/useAuth'
import { useConversations } from './hooks/useConversations'
import AuthScreen from './components/Auth/AuthScreen'
import Sidebar from './components/Sidebar/Sidebar'
import ChatArea from './components/Chat/ChatArea'
import CalculatorScreen from './components/Calculator/CalculatorScreen'
import ProfileScreen from './components/Profile/ProfileScreen'

export default function App() {
  const { user, login, signup, logout } = useAuth()
  const [view, setView] = useState('chat')
  const { conversations, currentId, refresh, select, create, remove } = useConversations()

  // 로그인 후 대화 목록 로드 + 가장 최근 대화 자동 선택
  useEffect(() => {
    if (!user) return
    refresh().then(list => {
      if (list.length > 0 && !currentId) select(list[0].id)
    })
  }, [user])

  // 메시지 전송 완료 후 대화 목록 갱신 (제목·타임스탬프 반영)
  const handleMessageSent = () => refresh()

  if (!user) {
    return <AuthScreen onLogin={login} onSignup={signup} />
  }

  const currentConversation = conversations.find(c => c.id === currentId)

  return (
    <div style={{ display: 'flex', width: '100%', height: '100dvh' }}>
      <Sidebar
        user={user}
        onLogout={logout}
        view={view}
        onViewChange={setView}
        conversations={conversations}
        currentConversationId={currentId}
        onSelectConversation={select}
        onCreateConversation={create}
        onDeleteConversation={remove}
      />
      {view === 'calculator' ? (
        <CalculatorScreen />
      ) : view === 'profile' ? (
        <ProfileScreen onLogout={logout} />
      ) : (
        <ChatArea
          user={user}
          conversationId={currentId}
          conversationTitle={currentConversation?.title}
          onMessageSent={handleMessageSent}
        />
      )}
    </div>
  )
}

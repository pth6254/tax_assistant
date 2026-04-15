import { useAuth } from './hooks/useAuth'
import AuthScreen from './components/Auth/AuthScreen'
import Sidebar from './components/Sidebar/Sidebar'
import ChatArea from './components/Chat/ChatArea'

export default function App() {
  const { user, login, signup, logout } = useAuth()

  if (!user) {
    return <AuthScreen onLogin={login} onSignup={signup} />
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100dvh' }}>
      <Sidebar user={user} onLogout={logout} />
      <ChatArea user={user} />
    </div>
  )
}

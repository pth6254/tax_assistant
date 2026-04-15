import { useState } from 'react'

const styles = {
  overlay: {
    position: 'fixed', inset: 0,
    background: 'var(--bg)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    animation: 'fadeIn .4s ease',
  },
  card: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 20,
    padding: '48px 44px',
    width: 400,
    display: 'flex', flexDirection: 'column', gap: 28,
  },
  logo: {
    fontFamily: 'var(--font-serif)',
    fontSize: 22,
    letterSpacing: '-0.5px',
  },
  tabs: {
    display: 'flex',
    borderBottom: '1px solid var(--border)',
  },
  input: {
    width: '100%',
    background: 'var(--surface2)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    padding: '13px 16px',
    color: 'var(--text)',
    fontFamily: 'var(--font-body)',
    fontSize: 14,
    outline: 'none',
  },
  label: {
    fontSize: 12,
    color: 'var(--text-muted)',
    letterSpacing: '.5px',
    textTransform: 'uppercase',
    marginBottom: 4,
    display: 'block',
  },
  btn: {
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 10,
    padding: 14,
    fontFamily: 'var(--font-body)',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    width: '100%',
  },
}

export default function AuthScreen({ onLogin, onSignup }) {
  const [tab, setTab] = useState('login')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [msg, setMsg] = useState({ text: '', type: '' })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!email || !pw) { setMsg({ text: '이메일과 비밀번호를 입력해주세요.', type: 'error' }); return }
    if (tab === 'signup' && pw !== pw2) { setMsg({ text: '비밀번호가 일치하지 않습니다.', type: 'error' }); return }

    setLoading(true)
    setMsg({ text: tab === 'login' ? '로그인 중…' : '가입 중…', type: '' })

    try {
      if (tab === 'signup') {
        await onSignup(email, pw)
        setMsg({ text: '가입 완료! 로그인해주세요.', type: 'success' })
        setTab('login')
        setPw('')
      } else {
        await onLogin(email, pw)
      }
    } catch (err) {
      setMsg({ text: err.detail || '요청에 실패했습니다.', type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const tabStyle = (t) => ({
    flex: 1, padding: 10,
    background: 'none', border: 'none',
    color: tab === t ? 'var(--accent2)' : 'var(--text-muted)',
    fontFamily: 'var(--font-body)',
    fontSize: 14, cursor: 'pointer',
    borderBottom: tab === t ? '2px solid var(--accent2)' : '2px solid transparent',
    marginBottom: -1,
  })

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        <div style={styles.logo}>세무 <span style={{ color: 'var(--accent2)' }}>AI</span> 어시스턴트</div>

        <div style={styles.tabs}>
          <button style={tabStyle('login')}  onClick={() => setTab('login')}>로그인</button>
          <button style={tabStyle('signup')} onClick={() => setTab('signup')}>회원가입</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={styles.label}>이메일</label>
            <input style={styles.input} type="email" placeholder="example@company.com"
              value={email} onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
          </div>
          <div>
            <label style={styles.label}>비밀번호</label>
            <input style={styles.input} type="password" placeholder="••••••••"
              value={pw} onChange={e => setPw(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
          </div>
          {tab === 'signup' && (
            <div>
              <label style={styles.label}>비밀번호 확인</label>
              <input style={styles.input} type="password" placeholder="••••••••"
                value={pw2} onChange={e => setPw2(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
            </div>
          )}
          <button style={{ ...styles.btn, opacity: loading ? 0.4 : 1 }}
            onClick={handleSubmit} disabled={loading}>
            {tab === 'login' ? '로그인' : '회원가입'}
          </button>
          {msg.text && (
            <div style={{
              fontSize: 13, textAlign: 'center',
              color: msg.type === 'error' ? 'var(--danger)' : msg.type === 'success' ? 'var(--success)' : 'var(--text-muted)'
            }}>{msg.text}</div>
          )}
        </div>
      </div>
    </div>
  )
}

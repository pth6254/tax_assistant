import { useState } from 'react'

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
    setMsg({ text: '', type: '' })

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

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'var(--bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      animation: 'fadeIn .4s ease',
      overflow: 'hidden',
    }}>
      {/* 배경 그라디언트 장식 */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 70% 50% at 50% 0%, rgba(79,124,255,.1) 0%, transparent 70%)',
      }} />
      <div style={{
        position: 'absolute',
        width: 500, height: 500, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(124,79,255,.07) 0%, transparent 70%)',
        top: '65%', left: '55%', transform: 'translate(-50%,-50%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'relative', zIndex: 1,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 24,
        padding: '44px 40px',
        width: 420,
        display: 'flex', flexDirection: 'column', gap: 26,
        boxShadow: '0 32px 80px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.06)',
        animation: 'slideUp .35s ease',
      }}>
        {/* 로고 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 13,
            background: 'linear-gradient(135deg, var(--accent) 0%, #7c4fff 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, flexShrink: 0,
            boxShadow: '0 6px 20px rgba(79,124,255,.4)',
          }}>
            ⚖
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, letterSpacing: '-0.4px', lineHeight: 1.2 }}>
              세무 <span style={{ color: 'var(--accent2)' }}>AI</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2, letterSpacing: '.3px' }}>
              Tax Assistant
            </div>
          </div>
        </div>

        {/* 탭 */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
          {[['login', '로그인'], ['signup', '회원가입']].map(([t, label]) => (
            <button
              key={t}
              onClick={() => { setTab(t); setMsg({ text: '', type: '' }) }}
              style={{
                flex: 1, padding: '10px 0',
                background: 'none', border: 'none',
                color: tab === t ? 'var(--accent2)' : 'var(--text-muted)',
                fontFamily: 'var(--font-body)', fontSize: 14, cursor: 'pointer',
                borderBottom: tab === t ? '2px solid var(--accent2)' : '2px solid transparent',
                marginBottom: -1,
                transition: 'color .15s',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 입력 필드 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <AuthField label="이메일" type="email" placeholder="example@company.com"
            value={email} onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
          <AuthField label="비밀번호" type="password" placeholder="••••••••"
            value={pw} onChange={e => setPw(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
          {tab === 'signup' && (
            <AuthField label="비밀번호 확인" type="password" placeholder="••••••••"
              value={pw2} onChange={e => setPw2(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
          )}

          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              marginTop: 4,
              background: loading ? 'rgba(79,124,255,.5)' : 'var(--accent)',
              color: '#fff', border: 'none', borderRadius: 12,
              padding: '14px', fontFamily: 'var(--font-body)',
              fontSize: 14, fontWeight: 500, cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'opacity .15s, transform .1s',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
            onMouseEnter={e => { if (!loading) e.currentTarget.style.opacity = '.88' }}
            onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
          >
            {loading && (
              <span style={{
                width: 14, height: 14,
                border: '2px solid rgba(255,255,255,.3)',
                borderTopColor: '#fff',
                borderRadius: '50%',
                animation: 'spin .7s linear infinite',
                display: 'inline-block', flexShrink: 0,
              }} />
            )}
            {tab === 'login' ? '로그인' : '회원가입'}
          </button>

          {msg.text && (
            <div style={{
              fontSize: 13, textAlign: 'center',
              padding: '9px 14px', borderRadius: 8,
              color: msg.type === 'error' ? 'var(--danger)' : msg.type === 'success' ? 'var(--success)' : 'var(--text-muted)',
              background: msg.type === 'error' ? 'rgba(255,92,92,.08)' : msg.type === 'success' ? 'rgba(76,175,125,.08)' : 'transparent',
            }}>
              {msg.text}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function AuthField({ label, ...props }) {
  return (
    <div>
      <label style={{
        fontSize: 11, color: 'var(--text-muted)',
        letterSpacing: '.6px', textTransform: 'uppercase',
        marginBottom: 7, display: 'block', fontWeight: 500,
      }}>
        {label}
      </label>
      <input
        {...props}
        style={{
          width: '100%',
          background: 'var(--surface2)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          padding: '13px 16px',
          color: 'var(--text)',
          fontFamily: 'var(--font-body)',
          fontSize: 14,
          transition: 'border-color .15s, box-shadow .15s',
        }}
      />
    </div>
  )
}

import { useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import { errorMessage } from '../../api/http'
export default function AuthScreen({ onLogin, onSignup }) {
  const [tab, setTab] = useState('login'), [email, setEmail] = useState(''), [pw, setPw] = useState(''), [pw2, setPw2] = useState('')
  const [message, setMessage] = useState(''), [success, setSuccess] = useState(false), [loading, setLoading] = useState(false)
  const submit = async e => {
    e.preventDefault()
    if (loading) return
    setSuccess(false); setMessage('')
    if (tab === 'signup' && pw !== pw2) { setMessage('비밀번호가 일치하지 않습니다.'); return }
    setLoading(true)
    try {
      if (tab === 'signup') { await onSignup(email, pw); setTab('login'); setPw(''); setPw2(''); setSuccess(true); setMessage('가입이 완료됐습니다. 로그인해 주세요.') }
      else await onLogin(email, pw)
    } catch (e) { setMessage(errorMessage(e)) } finally { setLoading(false) }
  }
  return <main className="auth-screen"><section className="auth-intro"><div className="brand"><span className="brand-mark"><Icon name="book" /></span><strong>세무 AI</strong></div><p className="eyebrow">EVIDENCE FIRST</p><h1>세무 질문에,<br />확인할 수 있는 근거를.</h1><p>법령 원문과 내 문서를 찾고,<br />계산의 조건과 과정을 함께 검토하세요.</p></section>
    <section className="auth-card"><h2>{tab === 'login' ? '다시 만나 반갑습니다.' : '나의 작업 공간 만들기'}</h2><p className="muted">세무 AI 어시스턴트에 {tab === 'login' ? '로그인' : '가입'}하세요.</p>
      <div className="auth-tabs">{[['login','로그인'],['signup','회원가입']].map(([key, label]) => <button key={key} type="button" disabled={loading} aria-pressed={tab === key} onClick={() => { setTab(key); setMessage('') }}>{label}</button>)}</div>
      <form onSubmit={submit}><div className="field"><label htmlFor="email">이메일</label><input id="email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="password">비밀번호</label><input id="password" type="password" required autoComplete={tab === 'login' ? 'current-password' : 'new-password'} value={pw} onChange={e => setPw(e.target.value)} /></div>
        {tab === 'signup' && <div className="field"><label htmlFor="password-confirm">비밀번호 확인</label><input id="password-confirm" type="password" required autoComplete="new-password" value={pw2} onChange={e => setPw2(e.target.value)} /></div>}
        <Notice tone={success ? 'info' : 'error'}>{message}</Notice><button className="button auth-submit" disabled={loading}>{loading ? '처리 중…' : tab === 'login' ? '로그인' : '회원가입'}</button>
      </form><p className="small muted">AI 답변은 참고 자료입니다. 최종 판단 전 근거와 적용 조건을 확인하세요.</p>
    </section></main>
}

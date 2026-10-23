import { useEffect, useState } from 'react'
import { serviceAvailable } from '../../api/authApi'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import { errorMessage } from '../../api/http'
const DEMO_VIDEO = 'https://github.com/pth6254/tax_assistant#readme'
export default function AuthScreen({ onLogin, onSignup, onGuest }) {
  const [online, setOnline] = useState(true)
  useEffect(() => { let active = true; serviceAvailable().then(ok => { if (active) setOnline(ok) }); return () => { active = false } }, [])
  const tryGuest = async () => {
    if (loading) return
    setSuccess(false); setMessage(''); setLoading(true)
    try { await onGuest() } catch (e) { setMessage(errorMessage(e, '체험 계정을 만들지 못했습니다.')) } finally { setLoading(false) }
  }
  const [tab, setTab] = useState('login'), [email, setEmail] = useState(''), [pw, setPw] = useState(''), [pw2, setPw2] = useState(''), [invite, setInvite] = useState('')
  const [message, setMessage] = useState(''), [success, setSuccess] = useState(false), [loading, setLoading] = useState(false)
  const submit = async e => {
    e.preventDefault()
    if (loading) return
    setSuccess(false); setMessage('')
    if (tab === 'signup' && pw !== pw2) { setMessage('비밀번호가 일치하지 않습니다.'); return }
    setLoading(true)
    try {
      if (tab === 'signup') { await onSignup(email, pw, invite); setTab('login'); setPw(''); setPw2(''); setSuccess(true); setMessage('가입이 완료됐습니다. 로그인해 주세요.') }
      else await onLogin(email, pw)
    } catch (e) { setMessage(errorMessage(e)) } finally { setLoading(false) }
  }
  return <main className="auth-screen"><section className="auth-intro"><div className="brand"><span className="brand-mark"><Icon name="book" /></span><strong>세무 AI</strong></div><p className="eyebrow">EVIDENCE FIRST</p><h1>세무 질문에,<br />확인할 수 있는 근거를.</h1><p>법령 원문과 내 문서를 찾고,<br />계산의 조건과 과정을 함께 검토하세요.</p></section>
    <section className="auth-card">{!online && <div className="notice" role="status">데모 서버가 지금 꺼져 있습니다(개인 PC에서 운영 중). <a href="{DEMO_VIDEO}" target="_blank" rel="noopener noreferrer">시연 영상과 화면 보기 ↗</a></div>}<h2>{tab === 'login' ? '다시 만나 반갑습니다.' : '나의 작업 공간 만들기'}</h2><p className="muted">세무 AI 어시스턴트에 {tab === 'login' ? '로그인' : '가입'}하세요.</p>
      <div className="auth-tabs">{[['login','로그인'],['signup','회원가입']].map(([key, label]) => <button key={key} type="button" disabled={loading} aria-pressed={tab === key} onClick={() => { setTab(key); setMessage('') }}>{label}</button>)}</div>
      <form onSubmit={submit}><div className="field"><label htmlFor="email">이메일</label><input id="email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="password">비밀번호</label><input id="password" type="password" required autoComplete={tab === 'login' ? 'current-password' : 'new-password'} value={pw} onChange={e => setPw(e.target.value)} /></div>
        {tab === 'signup' && <div className="field"><label htmlFor="password-confirm">비밀번호 확인</label><input id="password-confirm" type="password" required autoComplete="new-password" value={pw2} onChange={e => setPw2(e.target.value)} /></div>}
        {tab === 'signup' && <div className="field"><label htmlFor="invite-code">초대 코드</label><input id="invite-code" autoComplete="off" value={invite} onChange={e => setInvite(e.target.value)} aria-describedby="invite-hint" /><span id="invite-hint" className="field-hint">서비스를 공유한 분께 받은 코드를 입력하세요.</span></div>}
        <Notice tone={success ? 'info' : 'error'}>{message}</Notice><button className="button auth-submit" disabled={loading}>{loading ? '처리 중…' : tab === 'login' ? '로그인' : '회원가입'}</button>
      </form>{tab === 'login' && <button type="button" className="button secondary auth-guest" disabled={loading || !online} onClick={tryGuest}>가입 없이 체험하기 (하루 3회)</button>}<div className="small muted service-notice">
        <p>AI 답변은 참고 자료이며 세무 대리나 전문가 상담을 대신하지 않습니다. 최종 판단 전 근거와 적용 조건을 확인하세요.</p>
        <p>질문과 근거 원문은 답변 생성을 위해 AI 제공자(OpenRouter를 통한 외부 모델)로 전송됩니다. 주민등록번호·계좌번호 같은 개인정보는 입력하지 마세요.</p>
        <p>테스트 운영 중인 서비스로, 이용자당 하루 질문 수가 제한됩니다.</p>
      </div>
    </section></main>
}

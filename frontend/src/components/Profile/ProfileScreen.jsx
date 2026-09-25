import { useState, useEffect } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
import { getMe, updateProfile, changePassword, deleteAccount } from '../../api/userApi'
import './profile.css'

const BUSINESS_TYPE_LABELS = {
  '법인':          '법인사업자',
  '개인_일반과세': '개인 일반과세자',
  '개인_간이과세': '개인 간이과세자',
}

export default function ProfileScreen({ onLogout, onOpenCalendar }) {
  const [profile, setProfile] = useState(null)
  const [fetching, setFetching] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    setFetching(true); setError('')
    getMe().then(data => { if (active) setProfile(data) }).catch(() => { if (active) setError('내 정보를 불러오지 못했습니다.') }).finally(() => { if (active) setFetching(false) })
    return () => { active = false }
  }, [reload])

  if (fetching) {
    return (
      <main className="profile-screen">
        <div style={{
          margin: 'auto', display: 'flex', alignItems: 'center', gap: 10,
          color: 'var(--text-muted)',
        }}>
          <span style={{
            width: 16, height: 16,
            border: '2px solid rgba(255,255,255,.1)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin .7s linear infinite',
            display: 'inline-block',
          }} />
          불러오는 중…
        </div>
      </main>
    )
  }

  return (
    <main className="profile-screen">
      <header className="page-header profile-header">
        <Icon name="user" />
        <h1>내 정보</h1>
      </header>

      <div className="profile-scroll">
        <div className="profile-content">
          <Notice onRetry={() => setReload(v => v + 1)}>{error}</Notice>
          <Card title="국세청 세무일정" icon="📅">
            <p className="profile-description">국세청에 게시된 월별 신고·납부 일정을 확인할 수 있습니다. 전체 일정이며 개인별 신고 의무를 자동 판정하지는 않습니다.</p>
            <button className="button secondary" onClick={onOpenCalendar}>세무일정 캘린더 열기</button>
          </Card>
          {profile && <ProfileSection profile={profile} onUpdated={setProfile} />}
          <PasswordSection />
          <DeleteSection onLogout={onLogout} />
        </div>
      </div>
    </main>
  )
}

function ProfileSection({ profile, onUpdated }) {
  const [name,  setName]  = useState(profile?.name  ?? '')
  const [phone, setPhone] = useState(profile?.phone ?? '')
  const [businessType, setBusinessType] = useState(profile?.business_type ?? '개인_일반과세')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true); setMsg('')
    try {
      await updateProfile({ name, phone, business_type: businessType })
      onUpdated(prev => ({ ...prev, name, phone, business_type: businessType }))
      setMsg('저장되었습니다.')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const initials = profile?.name
    ? profile.name.slice(0, 2)
    : (profile?.email?.[0] || '?').toUpperCase()

  return (
    <Card title="프로필 정보" icon="🧑">
      {/* 아바타 */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
        <div style={{
          width: 72, height: 72, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent), #7c4fff)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 24, fontWeight: 700, color: '#fff',
          boxShadow: '0 6px 24px rgba(79,124,255,.35)',
          letterSpacing: '-1px',
        }}>
          {initials}
        </div>
      </div>

      <form onSubmit={handleSave} className="profile-form">
        <Field label="이메일">
          <input value={profile?.email ?? ''} disabled className="profile-input" />
        </Field>
        <Field label="이름">
          <input value={name} onChange={e => setName(e.target.value)}
            placeholder="이름을 입력하세요" maxLength={50} className="profile-input" />
        </Field>
        <Field label="전화번호">
          <input value={phone} onChange={e => setPhone(e.target.value)}
            placeholder="010-0000-0000" maxLength={20} className="profile-input" />
        </Field>
        <Field label="사업자 유형" hint="현재 공식 일정은 전체 일정으로 표시됩니다">
          <select value={businessType} onChange={e => setBusinessType(e.target.value)} className="profile-input">
            {Object.entries(BUSINESS_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        {msg && <StatusMsg text={msg} error={!msg.includes('저장')} />}
        <button type="submit" disabled={saving} className="button profile-primary">
          {saving ? '저장 중…' : '저장'}
        </button>
      </form>
    </Card>
  )
}

function PasswordSection() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const set = (key) => (e) => setForm(prev => ({ ...prev, [key]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (form.next !== form.confirm) { setMsg('새 비밀번호가 일치하지 않습니다.'); return }
    if (form.next.length < 8)       { setMsg('새 비밀번호는 8자 이상이어야 합니다.'); return }
    setSaving(true); setMsg('')
    try {
      await changePassword({ current_password: form.current, new_password: form.next })
      setForm({ current: '', next: '', confirm: '' })
      setMsg('비밀번호가 변경되었습니다.')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="비밀번호 변경" icon="🔑">
      <form onSubmit={handleSubmit} className="profile-form">
        <Field label="현재 비밀번호">
          <input type="password" value={form.current} onChange={set('current')} className="profile-input" required />
        </Field>
        <Field label="새 비밀번호" hint="8자 이상">
          <input type="password" value={form.next} onChange={set('next')} className="profile-input" required />
        </Field>
        <Field label="새 비밀번호 확인">
          <input type="password" value={form.confirm} onChange={set('confirm')} className="profile-input" required />
        </Field>
        {msg && <StatusMsg text={msg} error={msg !== '비밀번호가 변경되었습니다.'} />}
        <button type="submit" disabled={saving} className="button profile-primary">
          {saving ? '변경 중…' : '비밀번호 변경'}
        </button>
      </form>
    </Card>
  )
}

function DeleteSection({ onLogout }) {
  const [open, setOpen]         = useState(false)
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError]       = useState('')

  const handleDelete = async (e) => {
    e.preventDefault()
    setDeleting(true); setError('')
    try {
      await deleteAccount({ password })
      onLogout()
    } catch (err) {
      setError(err.message)
      setDeleting(false)
    }
  }

  return (
    <Card title="계정 삭제" icon="⚠️" danger>
      <p className="profile-description">
        계정을 삭제하면 업로드한 문서와 채팅 내역이 모두 삭제되며 복구할 수 없습니다.
      </p>
      {!open ? (
        <button onClick={() => setOpen(true)} className="button profile-danger">계정 삭제</button>
      ) : (
        <form onSubmit={handleDelete} className="profile-form">
          <Field label="비밀번호 확인">
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="현재 비밀번호 입력" className="profile-input" required autoFocus />
          </Field>
          {error && <StatusMsg text={error} error />}
          <div className="profile-danger-actions">
            <button type="button" onClick={() => { setOpen(false); setPassword(''); setError('') }} className="button secondary">
              취소
            </button>
            <button type="submit" disabled={deleting} className="button profile-danger">
              {deleting ? '삭제 중…' : '영구 삭제 확인'}
            </button>
          </div>
        </form>
      )}
    </Card>
  )
}

// ── 공통 UI ──────────────────────────────────────────────────────────

function Card({ title, icon, children, danger }) {
  return (
    <section className={'profile-card' + (danger ? ' profile-card-danger' : '')}>
      <header className="profile-card-header">
        {icon && <span className="profile-card-icon" aria-hidden="true">{icon}</span>}
        <h2>{title}</h2>
      </header>
      <div className="profile-card-body">{children}</div>
    </section>
  )
}

function Field({ label, hint, children }) {
  return (
    <label className="profile-field">
      <span className="profile-field-label">
        {label}
        {hint && <span className="profile-field-hint">({hint})</span>}
      </span>
      {children}
    </label>
  )
}

function StatusMsg({ text, error }) {
  return (
    <div className={'profile-status' + (error ? ' profile-status-error' : '')} role="status">
      {text}
    </div>
  )
}

import { useState, useEffect } from 'react'
import { getMe, updateProfile, changePassword, deleteAccount } from '../../api/userApi'

export default function ProfileScreen({ onLogout }) {
  const [profile, setProfile] = useState(null)
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    getMe().then(setProfile).catch(() => {}).finally(() => setFetching(false))
  }, [])

  if (fetching) {
    return (
      <main style={mainStyle}>
        <div style={{ color: 'var(--text-muted)', margin: 'auto' }}>불러오는 중...</div>
      </main>
    )
  }

  return (
    <main style={mainStyle}>
      <header style={{
        padding: '20px 32px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
      }}>
        <span style={{ fontSize: 18 }}>👤</span>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 400 }}>내 정보</h1>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 520 }}>
        <ProfileSection profile={profile} onUpdated={setProfile} />
        <PasswordSection />
        <DeleteSection onLogout={onLogout} />
      </div>
    </main>
  )
}

// ── 프로필 수정 ─────────────────────────────────────────────────────

function ProfileSection({ profile, onUpdated }) {
  const [name,  setName]  = useState(profile?.name  ?? '')
  const [phone, setPhone] = useState(profile?.phone ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      await updateProfile({ name, phone })
      onUpdated(prev => ({ ...prev, name, phone }))
      setMsg('저장되었습니다.')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="프로필 정보">
      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="이메일">
          <input value={profile?.email ?? ''} disabled style={{ ...inputStyle, opacity: 0.5, cursor: 'not-allowed' }} />
        </Field>
        <Field label="이름">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="이름을 입력하세요"
            maxLength={50}
            style={inputStyle}
          />
        </Field>
        <Field label="전화번호">
          <input
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="010-0000-0000"
            maxLength={20}
            style={inputStyle}
          />
        </Field>
        {msg && <StatusMsg text={msg} error={!msg.includes('저장')} />}
        <button type="submit" disabled={saving} style={primaryBtn}>
          {saving ? '저장 중...' : '저장'}
        </button>
      </form>
    </Card>
  )
}

// ── 비밀번호 변경 ───────────────────────────────────────────────────

function PasswordSection() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const set = (key) => (e) => setForm(prev => ({ ...prev, [key]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (form.next !== form.confirm) {
      setMsg('새 비밀번호가 일치하지 않습니다.')
      return
    }
    if (form.next.length < 8) {
      setMsg('새 비밀번호는 8자 이상이어야 합니다.')
      return
    }
    setSaving(true)
    setMsg('')
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

  const isSuccess = msg === '비밀번호가 변경되었습니다.'

  return (
    <Card title="비밀번호 변경">
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="현재 비밀번호">
          <input type="password" value={form.current} onChange={set('current')} style={inputStyle} required />
        </Field>
        <Field label="새 비밀번호" hint="8자 이상">
          <input type="password" value={form.next} onChange={set('next')} style={inputStyle} required />
        </Field>
        <Field label="새 비밀번호 확인">
          <input type="password" value={form.confirm} onChange={set('confirm')} style={inputStyle} required />
        </Field>
        {msg && <StatusMsg text={msg} error={!isSuccess} />}
        <button type="submit" disabled={saving} style={primaryBtn}>
          {saving ? '변경 중...' : '비밀번호 변경'}
        </button>
      </form>
    </Card>
  )
}

// ── 계정 삭제 ───────────────────────────────────────────────────────

function DeleteSection({ onLogout }) {
  const [open, setOpen]       = useState(false)
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError]     = useState('')

  const handleDelete = async (e) => {
    e.preventDefault()
    setDeleting(true)
    setError('')
    try {
      await deleteAccount({ password })
      onLogout()
    } catch (err) {
      setError(err.message)
      setDeleting(false)
    }
  }

  return (
    <Card title="계정 삭제" danger>
      <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        계정을 삭제하면 업로드한 문서와 채팅 내역이 모두 삭제되며 복구할 수 없습니다.
      </p>

      {!open ? (
        <button onClick={() => setOpen(true)} style={dangerBtn}>계정 삭제</button>
      ) : (
        <form onSubmit={handleDelete} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label="비밀번호 확인">
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="현재 비밀번호 입력"
              style={inputStyle}
              required
              autoFocus
            />
          </Field>
          {error && <StatusMsg text={error} error />}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={() => { setOpen(false); setPassword(''); setError('') }} style={ghostBtn}>
              취소
            </button>
            <button type="submit" disabled={deleting} style={dangerBtn}>
              {deleting ? '삭제 중...' : '영구 삭제 확인'}
            </button>
          </div>
        </form>
      )}
    </Card>
  )
}

// ── 공통 UI ─────────────────────────────────────────────────────────

function Card({ title, children, danger }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${danger ? 'rgba(255,92,92,.3)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '14px 20px',
        borderBottom: `1px solid ${danger ? 'rgba(255,92,92,.2)' : 'var(--border)'}`,
        fontSize: 13, fontWeight: 500,
        color: danger ? 'var(--danger)' : 'var(--text)',
      }}>
        {title}
      </div>
      <div style={{ padding: '20px' }}>{children}</div>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {label}
        {hint && <span style={{ marginLeft: 6, opacity: 0.7 }}>({hint})</span>}
      </label>
      {children}
    </div>
  )
}

function StatusMsg({ text, error }) {
  return (
    <div style={{
      fontSize: 12, padding: '8px 12px', borderRadius: 8,
      color: error ? 'var(--danger)' : 'var(--success)',
      background: error ? 'rgba(255,92,92,.08)' : 'rgba(76,175,125,.08)',
    }}>
      {text}
    </div>
  )
}

// ── 스타일 상수 ─────────────────────────────────────────────────────

const mainStyle = {
  flex: 1, display: 'flex', flexDirection: 'column',
  background: 'var(--bg)', minWidth: 0, overflow: 'hidden',
}

const inputStyle = {
  width: '100%',
  background: 'var(--surface2)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '9px 12px',
  color: 'var(--text)',
  fontSize: 14,
  outline: 'none',
}

const primaryBtn = {
  padding: '10px',
  background: 'var(--accent)',
  color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 13, cursor: 'pointer',
}

const dangerBtn = {
  flex: 1,
  padding: '10px',
  background: 'rgba(255,92,92,.12)',
  color: 'var(--danger)',
  border: '1px solid rgba(255,92,92,.3)',
  borderRadius: 8,
  fontSize: 13, cursor: 'pointer',
}

const ghostBtn = {
  padding: '10px 16px',
  background: 'var(--surface2)',
  color: 'var(--text-muted)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  fontSize: 13, cursor: 'pointer',
}

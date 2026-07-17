import { useState, useEffect } from 'react'
import { getMe, updateProfile, changePassword, deleteAccount } from '../../api/userApi'
import { getTaxSchedule } from '../../api/taxScheduleApi'

const BUSINESS_TYPE_LABELS = {
  '법인':          '법인사업자',
  '개인_일반과세': '개인 일반과세자',
  '개인_간이과세': '개인 간이과세자',
}

export default function ProfileScreen({ onLogout }) {
  const [profile, setProfile] = useState(null)
  const [fetching, setFetching] = useState(true)

  useEffect(() => {
    getMe().then(setProfile).catch(() => {}).finally(() => setFetching(false))
  }, [])

  if (fetching) {
    return (
      <main style={mainStyle}>
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
    <main style={mainStyle}>
      <header style={{
        padding: '18px 32px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        background: 'rgba(24,28,39,.8)',
        backdropFilter: 'blur(8px)',
      }}>
        <span style={{ fontSize: 18 }}>👤</span>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 17, fontWeight: 400 }}>내 정보</h1>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 540 }}>
        <TaxScheduleSection businessType={profile?.business_type} />
        <ProfileSection profile={profile} onUpdated={setProfile} />
        <PasswordSection />
        <DeleteSection onLogout={onLogout} />
      </div>
    </main>
  )
}

function TaxScheduleSection({ businessType }) {
  const [items, setItems] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getTaxSchedule()
      .then(data => setItems(data.items))
      .catch(err => setError(err.message))
  }, [businessType])

  return (
    <Card title="다가오는 세무 일정" icon="📅">
      {error && <StatusMsg text={error} error />}
      {!error && !items && (
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>불러오는 중…</div>
      )}
      {items && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.map((item, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 14px',
              background: item.d_day <= 7 ? 'rgba(255,92,92,.06)' : 'var(--surface2)',
              border: `1px solid ${item.d_day <= 7 ? 'rgba(255,92,92,.2)' : 'var(--border)'}`,
              borderRadius: 9,
            }}>
              <div>
                <div style={{ fontSize: 13, color: 'var(--text)' }}>
                  <span style={{ color: 'var(--accent2)', marginRight: 6 }}>{item.tax_type}</span>
                  {item.label}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{item.due_date}</div>
              </div>
              <div style={{
                fontSize: 13, fontWeight: 600,
                color: item.d_day <= 7 ? 'var(--danger)' : 'var(--accent2)',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {item.d_day === 0 ? '오늘' : `D-${item.d_day}`}
              </div>
            </div>
          ))}
        </div>
      )}
      <p style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginTop: 14 }}>
        * 일반적인 신고 기한 안내이며 법적 효력이 없습니다. 성실신고확인대상자 등 예외는 세무사와 상담하세요.
      </p>
    </Card>
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

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="이메일">
          <input value={profile?.email ?? ''} disabled style={{ ...inputStyle, opacity: 0.45, cursor: 'not-allowed' }} />
        </Field>
        <Field label="이름">
          <input value={name} onChange={e => setName(e.target.value)}
            placeholder="이름을 입력하세요" maxLength={50} style={inputStyle} />
        </Field>
        <Field label="전화번호">
          <input value={phone} onChange={e => setPhone(e.target.value)}
            placeholder="010-0000-0000" maxLength={20} style={inputStyle} />
        </Field>
        <Field label="사업자 유형" hint="세무 일정 계산에 사용됩니다">
          <select value={businessType} onChange={e => setBusinessType(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
            {Object.entries(BUSINESS_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        {msg && <StatusMsg text={msg} error={!msg.includes('저장')} />}
        <button type="submit" disabled={saving} style={primaryBtn}>
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
        {msg && <StatusMsg text={msg} error={msg !== '비밀번호가 변경되었습니다.'} />}
        <button type="submit" disabled={saving} style={primaryBtn}>
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
      <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.65, marginBottom: 14 }}>
        계정을 삭제하면 업로드한 문서와 채팅 내역이 모두 삭제되며 복구할 수 없습니다.
      </p>
      {!open ? (
        <button onClick={() => setOpen(true)} style={dangerBtn}>계정 삭제</button>
      ) : (
        <form onSubmit={handleDelete} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label="비밀번호 확인">
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="현재 비밀번호 입력" style={inputStyle} required autoFocus />
          </Field>
          {error && <StatusMsg text={error} error />}
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={() => { setOpen(false); setPassword(''); setError('') }} style={ghostBtn}>
              취소
            </button>
            <button type="submit" disabled={deleting} style={dangerBtn}>
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
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${danger ? 'rgba(255,92,92,.25)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '13px 20px',
        borderBottom: `1px solid ${danger ? 'rgba(255,92,92,.15)' : 'var(--border)'}`,
        display: 'flex', alignItems: 'center', gap: 8,
        background: danger ? 'rgba(255,92,92,.04)' : 'rgba(255,255,255,.02)',
      }}>
        {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
        <span style={{ fontSize: 13, fontWeight: 500, color: danger ? 'var(--danger)' : 'var(--text)' }}>
          {title}
        </span>
      </div>
      <div style={{ padding: '20px' }}>{children}</div>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '.4px', fontWeight: 500 }}>
        {label}
        {hint && <span style={{ marginLeft: 6, fontWeight: 400, opacity: .7 }}>({hint})</span>}
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
      border: `1px solid ${error ? 'rgba(255,92,92,.2)' : 'rgba(76,175,125,.2)'}`,
    }}>
      {text}
    </div>
  )
}

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
  transition: 'border-color .15s, box-shadow .15s',
}

const primaryBtn = {
  padding: '10px 16px',
  background: 'var(--accent)',
  color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 13, fontWeight: 500, cursor: 'pointer',
  transition: 'opacity .15s',
}

const dangerBtn = {
  flex: 1,
  padding: '10px 16px',
  background: 'rgba(255,92,92,.1)',
  color: 'var(--danger)',
  border: '1px solid rgba(255,92,92,.25)',
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

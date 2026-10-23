// Vite proxy를 통해 /api 요청이 로컬 FastAPI(8001)로 전달됨
// credentials: 'include' 로 httpOnly 쿠키 자동 전송

export const login = async (email, password) => {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password }),
  })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}

export const signup = async (email, password, inviteCode = '') => {
  const res = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password, invite_code: inviteCode }),
  })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}

export const startGuest = async () => {
  const res = await fetch('/api/auth/guest', { method: 'POST', credentials: 'include' })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw data
  return data
}

// The demo server is a home PC behind a tunnel; the page stays up on Vercel when it is off.
export const serviceAvailable = async () => {
  try {
    const res = await fetch('/api/health/ready', { cache: 'no-store' })
    return res.ok
  } catch { return false }
}

export const logout = async () => {
  await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
  })
}

const api = async (path, options = {}) => {
  const res = await fetch(`/api/users${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '오류가 발생했습니다.')
  return data
}

export const getMe          = ()     => api('/me')
export const updateProfile  = (body) => api('/me',          { method: 'PATCH',  body: JSON.stringify(body) })
export const changePassword = (body) => api('/me/password', { method: 'PATCH',  body: JSON.stringify(body) })
export const deleteAccount  = (body) => api('/me',          { method: 'DELETE', body: JSON.stringify(body) })

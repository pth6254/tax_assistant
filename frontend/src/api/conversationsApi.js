const api = async (path, options = {}) => {
  const res = await fetch(`/api/conversations${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error((await res.json()).detail || '오류')
  return res.json()
}

export const listConversations  = ()            => api('')
export const createConversation = ()            => api('', { method: 'POST' })
export const getMessages        = (id)          => api(`/${id}/messages`)
export const renameConversation = (id, title)   => api(`/${id}`, { method: 'PATCH',  body: JSON.stringify({ title }) })
export const deleteConversation = (id)          => api(`/${id}`, { method: 'DELETE' })

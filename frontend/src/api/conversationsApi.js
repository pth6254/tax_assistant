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
export const reviseConversation = (id, expected_message_id, query) => api(`/${id}/revise`, {
  method: 'POST', body: JSON.stringify({ expected_message_id, ...(query === undefined ? {} : { query }) }),
})
export const selectAnswerVersion = (id, messageId, version, expectedVersion) => api(`/${id}/answers/${messageId}/version`, {
  method: 'PUT', body: JSON.stringify({ expected_message_id: messageId, expected_version: expectedVersion, version }),
})
export const renameConversation = (id, title)   => api(`/${id}`, { method: 'PATCH',  body: JSON.stringify({ title }) })
export const deleteConversation = (id)          => api(`/${id}`, { method: 'DELETE' })

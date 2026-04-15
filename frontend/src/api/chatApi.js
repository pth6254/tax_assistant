export const sendChat = async (query, userId) => {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, userId }),
  })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}

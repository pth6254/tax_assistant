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

export const streamChat = async (query, userId, onChunk, onDone) => {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, userId }),
  })
  if (!res.ok) throw await res.json()

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer    = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop()  // 마지막 불완전한 청크는 보관

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') { onDone?.(); return }
      try {
        const { chunk } = JSON.parse(payload)
        onChunk(chunk)
      } catch { /* 파싱 실패 무시 */ }
    }
  }
  onDone?.()
}

export const sendChat = async (query, conversationId) => {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, conversation_id: conversationId }),
  })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}

export const streamChat = async (query, conversationId, onChunk, onDone, onCalc) => {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, conversation_id: conversationId }),
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
        const event = JSON.parse(payload)
        if (event.type === 'calc') onCalc?.({ tool: event.tool, params: event.params })
        else if (event.type === 'chunk') onChunk(event.text)
      } catch { /* 파싱 실패 무시 */ }
    }
  }
  onDone?.()
}

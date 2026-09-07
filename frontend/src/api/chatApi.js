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

export const streamChat = async (query, conversationId, onChunk, onDone, onCalc, onTool, signal) => {
  const res = await fetch('/api/chat/stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    credentials: 'include', signal,
    body: JSON.stringify({ query, conversation_id: conversationId }),
  })
  if (!res.ok) throw await res.json()
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) throw new Error('응답 연결이 중단되었습니다. 완료 여부를 확인해주세요.')
      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      const frames = buffer.split('\n\n')
      buffer = frames.pop()
      for (const frame of frames) {
        const payload = frame.split('\n').filter(l => l.startsWith('data:'))
          .map(l => l.slice(5).trimStart()).join('\n')
        if (!payload) continue
        if (payload === '[DONE]') { onDone?.(); return }
        const event = JSON.parse(payload)
        if (event.type === 'tool') onTool?.(event)
        else if (event.type === 'calc') onCalc?.({ tool: event.tool, params: event.params })
        else if (event.type === 'chunk') onChunk(event.text)
        else if (event.type === 'error') throw new Error(event.message || '응답 생성에 실패했습니다.')
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

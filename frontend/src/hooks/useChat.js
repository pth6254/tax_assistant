import { useState, useEffect, useRef } from 'react'
import { streamChat } from '../api/chatApi'
import { getMessages } from '../api/conversationsApi'
import { mergeTool, interruptTools } from '../components/Chat/toolState'

export const useChat = (conversationId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const request = useRef(null)
  const revision = useRef(0)

  useEffect(() => {
    const version = ++revision.current
    request.current?.abort()
    request.current = null
    setLoading(false)
    setMessages([])
    if (conversationId) getMessages(conversationId).then(msgs => {
      if (revision.current === version) setMessages(msgs.map(m => ({
        role: m.role, content: m.content, tools: m.tools || [],
      })))
    }).catch(() => {})
    return () => {
      ++revision.current
      request.current?.abort()
      request.current = null
    }
  }, [conversationId])

  const sendMessage = async (query, onDone) => {
    if (!conversationId || request.current) return
    ++revision.current
    const controller = new AbortController()
    request.current = controller
    const id = crypto.randomUUID()
    const update = change => {
      if (request.current !== controller) return
      setMessages(prev => prev.map(m => m.id === id ? change(m) : m))
    }
    setMessages(prev => [...prev,
      { role: 'user', content: query },
      { id, role: 'assistant', content: '', tools: [] },
    ])
    setLoading(true)
    try {
      await streamChat(query, conversationId,
        chunk => update(m => ({ ...m, content: m.content + chunk })),
        () => { if (request.current === controller) onDone?.() },
        calc => update(m => ({ ...m, calc })),
        event => update(m => ({ ...m, tools: mergeTool(m.tools, event) })),
        controller.signal,
      )
    } catch (err) {
      if (err.name !== 'AbortError') update(m => ({
        ...m, tools: interruptTools(m.tools),
        content: m.content + '\n\n⚠️ ' + (err.message || err.detail || '오류가 발생했습니다.'),
      }))
    } finally {
      if (request.current === controller) {
        request.current = null
        setLoading(false)
      }
    }
  }
  return { messages, loading, sendMessage }
}

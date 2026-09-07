import { useState, useEffect, useRef, useCallback } from 'react'
import { streamChat } from '../api/chatApi'
import { getMessages } from '../api/conversationsApi'
import { mergeTool, interruptTools } from '../components/Chat/toolState'
import { errorMessage } from '../api/http'

export const useChat = (conversationId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [reload, setReload] = useState(0)
  const [loadedId, setLoadedId] = useState(null)
  const request = useRef(null), revision = useRef(0)
  useEffect(() => {
    const version = ++revision.current
    request.current?.abort(); request.current = null
    setLoading(false); setMessages([]); setHistoryError('')
    setHistoryLoading(!!conversationId)
    setLoadedId(null)
    if (conversationId) getMessages(conversationId).then(msgs => {
      if (revision.current === version) setMessages(msgs.map((m, i) => ({ ...m, id: 'saved-' + i, tools: m.tools || [] })))
    }).catch(e => {
      if (revision.current === version) setHistoryError(errorMessage(e, '대화 이력을 불러오지 못했습니다.'))
    }).finally(() => { if (revision.current === version) { setHistoryLoading(false); setLoadedId(conversationId) } })
    return () => { ++revision.current; request.current?.abort(); request.current = null }
  }, [conversationId, reload])

  const stop = useCallback(() => {
    if (!request.current) return
    request.current.abort(); request.current = null
    setLoading(false)
    setMessages(prev => prev.map(m => m.status === 'streaming' ? { ...m, status: 'stopped', tools: interruptTools(m.tools) } : m))
  }, [])

  const sendMessage = async (query, onDone) => {
    if (!conversationId || loadedId !== conversationId || !query?.trim() || request.current || historyLoading || historyError) return
    ++revision.current
    const controller = new AbortController()
    request.current = controller
    const id = crypto.randomUUID()
    const update = change => {
      if (request.current !== controller) return
      setMessages(prev => prev.map(m => m.id === id ? change(m) : m))
    }
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content: query },
      { id, role: 'assistant', content: '', tools: [], status: 'streaming', query }])
    setLoading(true)
    try {
      await streamChat(query, conversationId,
        chunk => update(m => ({ ...m, content: m.content + chunk })),
        () => { if (request.current === controller) onDone?.() },
        calc => update(m => ({ ...m, calc })),
        event => update(m => ({ ...m, tools: mergeTool(m.tools, event) })),
        controller.signal)
      update(m => ({ ...m, status: 'complete' }))
    } catch (e) {
      if (e.name !== 'AbortError') update(m => ({ ...m, tools: interruptTools(m.tools), status: 'error', error: errorMessage(e) }))
    } finally {
      if (request.current === controller) { request.current = null; setLoading(false) }
    }
  }
  return { messages, loading, historyLoading: historyLoading || (!!conversationId && loadedId !== conversationId), historyError, retryHistory: () => setReload(n => n + 1), sendMessage, stop }
}

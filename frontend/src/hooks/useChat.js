import { useState, useEffect, useRef, useCallback } from 'react'
import { streamChat } from '../api/chatApi'
import { getMessages, selectAnswerVersion } from '../api/conversationsApi'
import { mergeTool, interruptTools } from '../components/Chat/toolState'
import { errorMessage } from '../api/http'

export const useChat = (conversationId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [versionLoading, setVersionLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [reload, setReload] = useState(0)
  const [loadedId, setLoadedId] = useState(null)
  const request = useRef(null), revision = useRef(0), versionSelection = useRef(false)
  useEffect(() => {
    const version = ++revision.current
    request.current?.abort(); request.current = null
    setLoading(false); setVersionLoading(false); setMessages([]); setHistoryError('')
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
    setMessages(prev => prev.map(m => m.status === 'streaming' ? (m.originalContent !== undefined
      ? { ...m, content: m.originalContent, tools: m.originalTools, status: 'complete', originalContent: undefined, originalTools: undefined }
      : { ...m, status: 'stopped', tools: interruptTools(m.tools) }) : m))
  }, [])

  const sendMessage = async (query, onDone) => {
    if (!conversationId || loadedId !== conversationId || !query?.trim() || request.current || versionSelection.current || historyLoading || historyError) return
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
        controller.signal,
        text => update(m => ({ ...m, content: text })))
      update(m => ({ ...m, status: 'complete' }))
      // Refresh server IDs only after DONE (the server has committed the turn).
      try {
        const saved = await getMessages(conversationId)
        if (request.current === controller) setMessages(saved.map((m, i) => ({ ...m, id: 'saved-' + i, tools: m.tools || [] })))
      } catch { /* Generation succeeded; missing IDs can be recovered by reloading history. */ }
    } catch (e) {
      if (e.name !== 'AbortError') update(m => ({ ...m, tools: interruptTools(m.tools), status: 'error', error: errorMessage(e) }))
    } finally {
      if (request.current === controller) { request.current = null; setLoading(false) }
    }
  }
  const regenerateAnswer = async (message, onDone) => {
    if (!conversationId || request.current || versionSelection.current || historyLoading || !message?.message_id) return
    const controller = new AbortController()
    request.current = controller
    const update = change => {
      if (request.current !== controller) return
      setMessages(prev => prev.map(m => m.message_id === message.message_id ? change(m) : m))
    }
    update(m => ({ ...m, originalContent: m.content, originalTools: m.tools, content: '', tools: [], status: 'streaming', error: undefined }))
    setLoading(true)
    try {
      await streamChat(null, conversationId,
        chunk => update(m => ({ ...m, content: m.content + chunk })),
        () => { if (request.current === controller) onDone?.() },
        calc => update(m => ({ ...m, calc })),
        event => update(m => ({ ...m, tools: mergeTool(m.tools, event) })),
        controller.signal,
        text => update(m => ({ ...m, content: text })),
        { expected_message_id: message.message_id, expected_version: message.answer_version || 1 })
      try {
        const saved = await getMessages(conversationId)
        if (request.current === controller) setMessages(saved.map((m, i) => ({ ...m, id: 'saved-' + i, tools: m.tools || [] })))
      } catch {
        update(m => ({ ...m, status: 'complete', originalContent: undefined, originalTools: undefined,
          answer_version: (m.answer_version_count || 1) + 1, answer_version_count: (m.answer_version_count || 1) + 1 }))
      }
    } catch (e) {
      if (e.name !== 'AbortError') update(m => ({ ...m, content: message.content, tools: message.tools, originalContent: undefined,
        originalTools: undefined, status: 'error', error: errorMessage(e) }))
    } finally {
      if (request.current === controller) { request.current = null; setLoading(false) }
    }
  }
  const chooseVersion = async (message, version) => {
    if (request.current || versionSelection.current || loading || historyLoading || !message?.message_id) return
    const currentRevision = revision.current
    versionSelection.current = true
    setVersionLoading(true)
    try {
      await selectAnswerVersion(conversationId, message.message_id, version, message.answer_version)
      const saved = await getMessages(conversationId)
      if (revision.current === currentRevision) setMessages(saved.map((m, i) => ({ ...m, id: 'saved-' + i, tools: m.tools || [] })))
    } finally { versionSelection.current = false; if (revision.current === currentRevision) setVersionLoading(false) }
  }
  return { messages, loading, versionLoading, historyLoading: historyLoading || (!!conversationId && loadedId !== conversationId), historyError, retryHistory: () => setReload(n => n + 1), sendMessage, regenerateAnswer, chooseVersion, stop }
}

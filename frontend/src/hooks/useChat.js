import { useState, useEffect } from 'react'
import { streamChat } from '../api/chatApi'
import { getMessages } from '../api/conversationsApi'

export const useChat = (conversationId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  // 대화 전환 시 해당 대화의 기존 메시지 로드
  useEffect(() => {
    setMessages([])
    if (!conversationId) return
    getMessages(conversationId)
      .then(msgs => setMessages(msgs.map(m => ({ role: m.role, content: m.content }))))
      .catch(() => {})
  }, [conversationId])

  const appendChunkToLastMessage = (chunk) => {
    setMessages(prev => {
      const updated = [...prev]
      const last    = updated[updated.length - 1]
      updated[updated.length - 1] = { ...last, content: last.content + chunk }
      return updated
    })
  }

  const attachCalcToLastMessage = (calc) => {
    setMessages(prev => {
      const updated = [...prev]
      const last    = updated[updated.length - 1]
      updated[updated.length - 1] = { ...last, calc }
      return updated
    })
  }

  const sendMessage = async (query, onDone) => {
    if (!conversationId) return
    setMessages(prev => [...prev,
      { role: 'user',      content: query },
      { role: 'assistant', content: '' },
    ])
    setLoading(true)

    try {
      await streamChat(query, conversationId, appendChunkToLastMessage, () => {
        setLoading(false)
        onDone?.()
      }, attachCalcToLastMessage)
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `⚠️ ${err.message || '오류가 발생했습니다.'}`,
        }
        return updated
      })
      setLoading(false)
    }
  }

  return { messages, loading, sendMessage }
}

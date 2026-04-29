import { useState } from 'react'
import { streamChat } from '../api/chatApi'

export const useChat = (userId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const appendChunkToLastMessage = (chunk) => {
    setMessages(prev => {
      const updated = [...prev]
      const last    = updated[updated.length - 1]
      updated[updated.length - 1] = { ...last, content: last.content + chunk }
      return updated
    })
  }

  const sendMessage = async (query) => {
    setMessages(prev => [...prev,
      { role: 'user',      content: query },
      { role: 'assistant', content: '' },   // 스트리밍 채워질 자리
    ])
    setLoading(true)

    try {
      await streamChat(
        query,
        userId,
        appendChunkToLastMessage,
        () => setLoading(false),
      )
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `⚠️ ${err.detail || '오류가 발생했습니다.'}`,
        }
        return updated
      })
      setLoading(false)
    }
  }

  const clearMessages = () => setMessages([])

  return { messages, loading, sendMessage, clearMessages }
}

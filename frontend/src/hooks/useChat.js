import { useState } from 'react'
import { sendChat } from '../api/chatApi'

export const useChat = (userId) => {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const sendMessage = async (query) => {
    // 사용자 메시지 즉시 추가
    setMessages(prev => [...prev, { role: 'user', content: query }])
    setLoading(true)

    try {
      const data = await sendChat(query, userId)
      setMessages(prev => [...prev, { role: 'assistant', content: data.output }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `⚠️ ${err.detail || '오류가 발생했습니다.'}`
      }])
    } finally {
      setLoading(false)
    }
  }

  const clearMessages = () => setMessages([])

  return { messages, loading, sendMessage, clearMessages }
}

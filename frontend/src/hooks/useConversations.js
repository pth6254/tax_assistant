import { useState, useCallback } from 'react'
import { listConversations, createConversation, deleteConversation } from '../api/conversationsApi'

export const useConversations = () => {
  const [conversations, setConversations] = useState([])
  const [currentId, setCurrentId] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const list = await listConversations()
      setConversations(list)
      return list
    } catch {
      return []
    }
  }, [])

  const select = useCallback((id) => setCurrentId(id), [])

  const create = useCallback(async () => {
    const conv = await createConversation()
    setConversations(prev => [conv, ...prev])
    setCurrentId(conv.id)
    return conv
  }, [])

  const remove = useCallback(async (id) => {
    await deleteConversation(id)
    setConversations(prev => {
      const next = prev.filter(c => c.id !== id)
      // 삭제된 대화가 현재 선택된 경우 다음 대화 선택
      setCurrentId(cur => cur === id ? (next[0]?.id ?? null) : cur)
      return next
    })
  }, [])

  const refreshTitles = useCallback(async () => {
    const list = await listConversations().catch(() => [])
    setConversations(list)
  }, [])

  return { conversations, currentId, refresh, select, create, remove, refreshTitles }
}

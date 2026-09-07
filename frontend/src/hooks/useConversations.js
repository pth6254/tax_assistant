import { useState, useCallback, useRef } from 'react'
import { listConversations, createConversation, deleteConversation } from '../api/conversationsApi'

export const useConversations = () => {
  const [conversations, setConversations] = useState([])
  const [error, setError] = useState('')
  const version = useRef(0)
  const [currentId, setCurrentId] = useState(null)

  const refresh = useCallback(async () => {
    const current = ++version.current
    setError('')
    try {
      const list = await listConversations()
      if (current === version.current) setConversations(list)
      return list
    } catch {
      if (current === version.current) setError('대화 목록을 불러오지 못했습니다.')
      return []
    }
  }, [])

  const select = useCallback((id) => setCurrentId(id), [])

  const create = useCallback(async () => {
    const conv = await createConversation()
    ++version.current
    setConversations(prev => [conv, ...prev])
    setCurrentId(conv.id)
    return conv
  }, [])

  const remove = useCallback(async (id) => {
    await deleteConversation(id)
    ++version.current
    setConversations(prev => {
      const next = prev.filter(c => c.id !== id)
      // 삭제된 대화가 현재 선택된 경우 다음 대화 선택
      setCurrentId(cur => cur === id ? (next[0]?.id ?? null) : cur)
      return next
    })
  }, [])

  return { error, conversations, currentId, refresh, select, create, remove }
}

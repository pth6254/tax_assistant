import { useEffect, useState } from 'react'
import { getDependencyHealth } from '../../api/healthApi'
export default function AiServiceStatus() {
  const [health, setHealth] = useState(null), [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    const refresh = async () => { try { const data = await getDependencyHealth(); if (active) { setHealth(data); setError(false) } } catch { if (active) setError(true) } }
    refresh(); const timer = setInterval(refresh, 30000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  const ok = health?.llm?.status === 'ok' && health?.embedding?.status === 'ok'
  return <details className="ai-status-details"><summary>{error ? 'AI 연결 확인 필요' : !health ? 'AI 상태 확인 중' : ok ? 'AI 연결됨' : 'AI 일부 기능 확인 필요'} ⌄</summary>
    <div className="ai-status-popover" aria-label="AI 서비스 상세 상태">{['llm','embedding'].map(key => <p key={key}><strong>{key === 'llm' ? '생성' : '임베딩'}</strong><br />{health?.[key]?.provider || '확인 중'} · {health?.[key]?.model || '모델 정보 없음'}<br />{health?.[key]?.status === 'ok' ? '연결 정상' : '연결 확인 필요'}</p>)}<p>연결 상태이며 답변 품질의 인증은 아닙니다.</p></div>
  </details>
}

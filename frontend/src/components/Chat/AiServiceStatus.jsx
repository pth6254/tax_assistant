import { useEffect, useState } from 'react'
import { getDependencyHealth } from '../../api/healthApi'

const ROLES = [
  { key: 'llm', role: '생성' },
  { key: 'embedding', role: '임베딩' },
]

function serviceLabel(role, service) {
  const provider = service?.provider ? service.provider.toUpperCase() : '확인 중'
  const version = service?.version ? ` ${service.version}` : ''
  const device = service?.device && service.device !== 'auto' ? ` · ${service.device.toUpperCase()}` : ''
  return `${provider} ${role}${version}${device}`
}

export default function AiServiceStatus() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const data = await getDependencyHealth()
        if (active) setHealth(data)
      } catch {
        if (active) setHealth({})
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 30_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  return (
    <div
      aria-label="AI 서비스 상태"
      style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}
    >
      {ROLES.map(({ key, role }) => {
        const service = health?.[key]
        const ok = service?.status === 'ok' || service?.status === 'disabled'
        const pending = health === null
        const model = service?.model || ''
        return (
          <span
            key={key}
            title={pending ? '상태 확인 중' : model || (ok ? '정상 연결' : '연결 확인 필요')}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              padding: '4px 8px', borderRadius: 999,
              border: `1px solid ${ok ? 'rgba(64,192,140,.28)' : 'var(--border)'}`,
              background: ok ? 'rgba(64,192,140,.08)' : 'var(--surface2)',
              color: ok ? 'var(--success)' : 'var(--text-muted)',
              fontSize: 10, whiteSpace: 'nowrap',
            }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: pending ? 'var(--text-muted)' : ok ? 'var(--success)' : 'var(--danger)',
            }} />
            {serviceLabel(role, service)}
          </span>
        )
      })}
    </div>
  )
}

export default function Notice({ children, onRetry, tone = 'error' }) {
  if (!children) return null
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
    <span>{children}</span>{onRetry && <button className="button secondary" onClick={onRetry}>다시 시도</button>}
  </div>
}

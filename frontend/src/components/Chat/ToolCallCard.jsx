import { TOOL_LABELS, STATUS_LABELS, isPendingTool } from './toolState'

export default function ToolCallCard({ tool, onCitationClick, onOpenCalculator }) {
  const pending = isPendingTool(tool)
  const success = tool.status === 'ok'
  const calc = success && !['none', 'law_lookup', 'document_search'].includes(tool.tool)
  return (
    <section style={{
      width: '100%', boxSizing: 'border-box', border: '1px solid var(--border)',
      borderRadius: 10, padding: '10px 14px', background: 'var(--surface2)',
      fontSize: 13, overflowWrap: 'anywhere',
    }} aria-label={TOOL_LABELS[tool.tool] || '도구'}>
      <div role="status" aria-live="polite" style={{ display: 'flex', gap: 10, justifyContent: 'space-between' }}>
        <strong>{TOOL_LABELS[tool.tool] || '도구'}</strong>
        <span style={{ color: success ? 'var(--success)' : 'var(--text-muted)' }}>
          {pending ? '◌ ' : ''}{STATUS_LABELS[tool.status] || '상태 확인 필요'}
        </span>
      </div>
      {tool.context && (
        <details open={!success} style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer' }}>{success ? '실행 결과 보기' : '상세 안내'}</summary>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', maxHeight: 260, overflow: 'auto', lineHeight: 1.6 }}>
            {tool.context}
          </pre>
        </details>
      )}
      {success && tool.tool === 'law_lookup' && tool.params?.law_name && tool.params?.article_no && onCitationClick && (
        <button className="tool-action" onClick={() => onCitationClick(tool.params.law_name, tool.params.article_no)}>
          조문 원문 열기 →
        </button>
      )}
      {calc && onOpenCalculator && (
        <button className="tool-action" onClick={() => onOpenCalculator(tool.tool, tool.params)}>
          계산기에서 조건 바꾸기 →
        </button>
      )}
    </section>
  )
}

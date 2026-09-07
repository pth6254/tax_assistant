import { TOOL_LABELS, STATUS_LABELS, isPendingTool } from './toolState'
import Icon from '../ui/Icon'
export default function ToolCallCard({ tool, onCitationClick, onOpenCalculator, onRetry }) {
  const pending = isPendingTool(tool), success = tool.status === 'ok'
  const calculator = !['none','law_lookup','document_search'].includes(tool.tool)
  return <section className={'tool-card ' + (pending ? 'pending' : success ? 'success' : 'failed')} aria-label={TOOL_LABELS[tool.tool] || '도구'}>
    <div className="tool-heading" role="status" aria-live="polite"><span className="tool-name">{pending ? <span className="spinner" /> : <Icon name={calculator ? 'calculator' : tool.tool === 'document_search' ? 'file' : 'book'} size={17} />}{TOOL_LABELS[tool.tool] || '도구'}</span><span className="status-text">{STATUS_LABELS[tool.status] || '확인 필요'}</span></div>
    {tool.context && <details open={!success && !pending}><summary>{success ? '실행 결과 보기' : '상세 안내'}</summary><pre>{tool.context}</pre></details>}
    <div className="tool-actions">
      {success && tool.tool === 'law_lookup' && tool.params?.law_name && tool.params?.article_no && onCitationClick && <button className="tool-action" onClick={() => onCitationClick(tool.params.law_name, tool.params.article_no)}>조문 원문 열기 →</button>}
      {success && calculator && onOpenCalculator && <button className="tool-action" onClick={() => onOpenCalculator(tool.tool, tool.params)}>계산기에서 조건 바꾸기 →</button>}
      {!success && !pending && tool.retryable && onRetry && <button className="tool-action" onClick={onRetry}>질문 다시 실행</button>}
      {!success && !pending && calculator && ['needs_input','invalid_arguments'].includes(tool.status) && onOpenCalculator && <button className="tool-action" onClick={() => onOpenCalculator(tool.tool, {})}>계산기에서 입력 확인</button>}
    </div>
  </section>
}

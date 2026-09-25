import { useEffect, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import ToolCallCard from './ToolCallCard'
import Notice from '../ui/Notice'
import Icon from '../ui/Icon'
const CITATION_RE = /\[(법률|시행령|시행규칙)\]\s*([^\n\[]+?)\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*항)?(?:\s*제\s*\d+\s*호(?:\s*의\s*\d+)?)?(?:\s*[가-힣]\s*목)?)/g
export default function MessageBubble({ message, onCitationClick, onOpenCalculator, onRetry, onEdit, onRegenerate }) {
  const isUser = message.role === 'user', body = useRef()
  const [editing, setEditing] = useState(false), [draft, setDraft] = useState(message.content)
  const [shareFeedback, setShareFeedback] = useState('')
  const shareAnswer = async () => {
    setShareFeedback('')
    try {
      if (navigator.share) {
        await navigator.share({ text: message.content })
      } else {
        await navigator.clipboard.writeText(message.content)
        setShareFeedback('답변을 복사했습니다.')
      }
    } catch (error) {
      if (error?.name !== 'AbortError') setShareFeedback('공유하지 못했습니다. 브라우저의 공유 또는 클립보드 권한을 확인해 주세요.')
    }
  }
  useEffect(() => {
    if (isUser || !body.current) return
    body.current.innerHTML = DOMPurify.sanitize(marked.parse(message.content || ''), {
      ALLOW_DATA_ATTR: false,
      FORBID_TAGS: ['img', 'video', 'audio', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'style'],
    })
    // Archive answers already have exact version links. Never open the current-law viewer.
    if (message.tools?.some(tool => tool.tool === 'history_lookup')) return
    // Link only text nodes after sanitization; model-generated attributes cannot become actions.
    const walker = document.createTreeWalker(body.current, NodeFilter.SHOW_TEXT)
    const nodes = []
    while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('a,code,pre,button')) nodes.push(walker.currentNode)
    for (const node of nodes) {
      const text = node.textContent, matches = [...text.matchAll(CITATION_RE)]
      if (!matches.length) continue
      const fragment = document.createDocumentFragment()
      let start = 0
      for (const match of matches) {
        fragment.append(text.slice(start, match.index))
        const button = document.createElement('button')
        button.type = 'button'; button.className = 'citation-link'; button.textContent = match[0]
        button.dataset.law = match[2].trim(); button.dataset.article = match[3].replace(/\s+/g, '')
        button.setAttribute('aria-label', match[0] + ' 원문 열기')
        fragment.append(button); start = match.index + match[0].length
      }
      fragment.append(text.slice(start)); node.replaceWith(fragment)
    }
  }, [message.content, message.tools, isUser])
  return <article className={'message ' + (isUser ? 'user-message' : 'assistant-message')}>
    {isUser ? <><div className="question-bubble">{editing && onEdit ? <form onSubmit={e => { e.preventDefault(); if (draft.trim()) { onEdit(draft.trim()); setEditing(false) } }}>
      <textarea aria-label="질문 수정" value={draft} maxLength={10000} rows={4} autoFocus onChange={e => setDraft(e.target.value)} style={{ width: '100%', minWidth: 200, resize: 'vertical' }} />
      <p className="small">원래 대화는 보존하고 별도 대화에서 다시 답변합니다.</p>
      <button className="button secondary" type="button" onClick={() => setEditing(false)}>취소</button>
      <button className="button secondary" type="submit" disabled={!draft.trim()}>수정 후 보내기</button>
    </form> : message.content}</div>
      {onEdit && !editing && <div className="message-actions user-actions"><button className="icon-button message-action" type="button" aria-label="마지막 질문 수정" title="질문 수정" onClick={() => { setDraft(message.content); setEditing(true) }}><Icon name="edit" size={17} /></button></div>}</> : <>
      <div className="answer-label"><Icon name="book" size={18} /><span>세무 AI</span><span className="muted small">근거와 적용 조건을 함께 확인하세요</span></div>
      {message.tools?.map(t => <ToolCallCard key={t.id} tool={t} onCitationClick={onCitationClick} onOpenCalculator={onOpenCalculator} onRetry={onRetry} />)}
      <div ref={body} className="markdown-bubble" onClick={e => { const target = e.target.closest('button.citation-link'); if (target && body.current.contains(target)) onCitationClick?.(target.dataset.law, target.dataset.article) }} />
      {message.status === 'stopped' && <Notice tone="info">생성을 중지했습니다. 표시된 내용은 미완성이고 저장되지 않았을 수 있습니다.</Notice>}
      {message.status === 'error' && <Notice onRetry={onRetry}>{message.error}</Notice>}
      {message.status === 'stopped' && onRetry && <button className="button secondary" onClick={onRetry}>같은 질문 다시 보내기</button>}
      {message.calc && !message.tools?.some(t => t.tool === message.calc.tool && t.status === 'ok') && <button className="button secondary" onClick={() => onOpenCalculator?.(message.calc.tool, message.calc.params)}>계산기에서 조건 바꾸기 →</button>}
      {(onRegenerate || (message.content && !['streaming', 'error', 'stopped'].includes(message.status))) && <div className="message-actions assistant-actions">
        {onRegenerate && <button className="icon-button message-action" type="button" aria-label="다시 답변" title="다시 답변 — 원본 대화는 보존됩니다" onClick={onRegenerate}><Icon name="refresh" size={18} /></button>}
        {message.content && !['streaming', 'error', 'stopped'].includes(message.status) && <button className="icon-button message-action" type="button" aria-label="답변 공유" title="답변 공유 또는 복사" onClick={shareAnswer}><Icon name="share" size={18} /></button>}
      </div>}
      {shareFeedback && <p className="share-feedback small" role="status">{shareFeedback}</p>}
    </>}
  </article>
}

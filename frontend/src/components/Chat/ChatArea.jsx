import { useEffect, useRef, useState } from 'react'
import { useChat } from '../../hooks/useChat'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'
import ArticleViewer from './ArticleViewer'
import AiServiceStatus from './AiServiceStatus'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
const QUESTIONS = ['소득세법 제55조 원문을 보여주세요', '내가 업로드한 계약서에서 지급 조건을 찾아주세요', '연소득 5천만원인 프리랜서의 소득세를 계산해주세요']
export default function ChatArea({ user, conversationId, conversationTitle, onMessageSent, onOpenCalculator, pendingQuestion, onPendingQuestionConsumed, onCreateConversation, library }) {
  const { messages, loading, historyLoading, historyError, retryHistory, sendMessage, stop } = useChat(conversationId)
  const [selected, setSelected] = useState(null), [unseen, setUnseen] = useState(false)
  const scroller = useRef(), follow = useRef(true), opener = useRef(null)
  useEffect(() => { setSelected(null); follow.current = true; setUnseen(false) }, [conversationId])
  const bottom = () => { if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight; follow.current = true; setUnseen(false) }
  useEffect(() => { if (follow.current) bottom(); else setUnseen(true) }, [messages])
  const send = query => { follow.current = true; sendMessage(query, onMessageSent) }
  useEffect(() => {
    if (pendingQuestion && conversationId && !historyLoading && !historyError) { send(pendingQuestion); onPendingQuestionConsumed?.() }
  }, [pendingQuestion, conversationId, historyLoading, historyError])
  const open = (lawName, articleNo) => { opener.current = document.activeElement; setSelected({ lawName, articleNo }) }
  const close = () => { setSelected(null); opener.current?.focus?.() }
  return <div className={'chat-layout ' + (selected ? 'with-source' : '')}>
    <main className="chat-main">
      <header className="page-header"><div><p className="eyebrow">TAX WORKSPACE</p><h1>{conversationTitle || '세무 상담'}</h1></div><AiServiceStatus /></header>
      <div className="messages-scroll" ref={scroller} onScroll={() => { const el = scroller.current; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 90; if (follow.current) setUnseen(false) }}>
        <div className="messages-content">
          <Notice onRetry={retryHistory}>{historyError}</Notice>
          {historyLoading && <p className="muted" role="status">대화 이력을 불러오고 있습니다…</p>}
          {!historyLoading && !historyError && !messages.length && <div className="chat-welcome">
            <span className="welcome-symbol"><Icon name="book" size={30} /></span><p className="eyebrow">근거부터 확인하는 세무 상담</p>
            <h2>복잡한 세무 질문,<br />근거와 함께 살펴보세요.</h2><p className="muted">법령 원문을 찾고, 내 문서를 검색하고,<br />계산 조건을 검토할 수 있습니다.</p>
            <div className="quick-questions">{QUESTIONS.map((q, i) => <button key={q} onClick={() => conversationId ? send(q) : onCreateConversation(q)}><Icon name={['book','file','calculator'][i]} /><span>{q}</span><Icon name="chevron" size={16} /></button>)}</div>
          </div>}
          {messages.map((m, i) => <MessageBubble key={m.id || i} message={m} userInitial={user.email?.[0]?.toUpperCase() || 'U'} onCitationClick={open} onOpenCalculator={onOpenCalculator} onRetry={loading || !m.query ? undefined : () => send(m.query)} />)}
          {loading && <div className="generation-status" role="status"><span className="spinner" />답변을 준비하고 있습니다. 필요하면 생성을 중지할 수 있습니다.</div>}
        </div>
      </div>
      {unseen && <button className="new-answer button secondary" onClick={bottom}><Icon name="down" size={16} />새 답변 보기</button>}
      {conversationId && <ChatInput onSend={send} disabled={loading || historyLoading || !!historyError} generating={loading} onStop={stop} library={library} />}
    </main>
    {selected && <ArticleViewer {...selected} onClose={close} />}
  </div>
}

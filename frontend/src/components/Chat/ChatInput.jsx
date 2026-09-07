import { useRef, useState } from 'react'
import Icon from '../ui/Icon'
import Notice from '../ui/Notice'
export default function ChatInput({ onSend, disabled, generating, onStop, library }) {
  const ref = useRef(), file = useRef(), composing = useRef(false)
  const [draft, setDraft] = useState('')
  const submit = () => {
    if (!draft.trim() || disabled) return
    onSend(draft.trim()); setDraft(''); ref.current.style.height = 'auto'
  }
  return <div className="composer-wrap">
    {library?.upload && <Notice tone={library.upload.status === 'error' ? 'error' : 'info'}>{library.upload.message}</Notice>}
    <div className="composer">
      <input ref={file} type="file" accept=".pdf" hidden onChange={e => { library?.add(e.target.files?.[0]); e.target.value = '' }} />
      <button className="icon-button" aria-label="PDF 파일 첨부" title="PDF 파일 첨부" disabled={library?.upload?.status === 'loading'} onClick={() => file.current.click()}><Icon name="plus" /></button>
      <textarea ref={ref} aria-label="세무 질문" placeholder="세무 질문을 입력하세요. 법령과 계산 근거를 함께 확인합니다." rows={1} value={draft}
        onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }}
        onChange={e => { setDraft(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 180) + 'px' }}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); submit() } }} />
      {generating ? <button className="send-button" aria-label="답변 생성 중지" title="답변 생성 중지" onClick={onStop}><Icon name="stop" /></button>
        : <button className="send-button" aria-label="질문 전송" title="질문 전송" disabled={disabled || !draft.trim()} onClick={submit}><Icon name="send" /></button>}
    </div>
    <p className="composer-help">Enter 전송 · Shift+Enter 줄바꿈 · 답변과 계산 결과는 적용 조건을 확인하세요.</p>
  </div>
}

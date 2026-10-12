// What a streaming answer shows while the server checks it. A verified answer arrives only
// after several model calls (about 40 seconds to 2 minutes), so the step, the elapsed time
// and the claims that already passed are shown instead of one unchanging line.
export const PROGRESS = {
  planning: '질문의 요청과 쟁점을 확인하고 있습니다',
  retrieving: '쟁점별 근거를 찾고 있습니다',
  assessing: '찾은 근거가 쟁점에 충분한지 확인하고 있습니다',
  generating: '확보한 근거로 답변을 작성하고 있습니다',
  checking: '답변의 근거와 조건을 대조하고 있습니다',
  repairing: '검사를 통과한 내용부터 보여 드립니다. 보류된 부분의 근거를 다시 찾아 보완하고 있습니다',
}

// The step is announced to screen readers; the ticking seconds are not.
export function progressParts(progress, seconds = 0) {
  const step = (PROGRESS[progress] || PROGRESS.checking) + '…'
  if (seconds < 1) return { step, elapsed: '' }
  return { step, elapsed: ` (${seconds}초${seconds >= 20 ? ' · 근거 검사까지 보통 1~2분 걸립니다' : ''})` }
}

export function progressText(progress, seconds = 0) {
  const { step, elapsed } = progressParts(progress, seconds)
  return step + elapsed
}

// The server sends the final answer once ('chunk'); before a repair round it may send the
// part that already passed ('draft'). The final answer replaces the draft, never follows it.
export function streamText(message, type, text) {
  if (type === 'draft') return { ...message, content: text, draft: true }
  if (type === 'replace') return { ...message, content: text, draft: false }
  return { ...message, content: message.draft ? text : message.content + text, draft: false }
}

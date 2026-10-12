import { test } from 'node:test'
import assert from 'node:assert/strict'
import { progressText, streamText } from '../src/components/Chat/answerProgress.js'

test('the waiting line names the step and the elapsed time', () => {
  assert.equal(progressText('planning', 0), '질문의 요청과 쟁점을 확인하고 있습니다…')
  assert.equal(progressText('assessing', 8), '찾은 근거가 쟁점에 충분한지 확인하고 있습니다… (8초)')
  assert.match(progressText('checking', 45), /\(45초 · 근거 검사까지 보통 1~2분 걸립니다\)$/)
  assert.match(progressText('unknown', 3), /^답변의 근거와 조건을 대조하고 있습니다/)
})

test('the final answer replaces a draft instead of being appended to it', () => {
  const start = { content: '', draft: false }
  const shown = streamText(start, 'draft', '## 핵심 판단\n통과한 내용')
  assert.deepEqual(shown, { content: '## 핵심 판단\n통과한 내용', draft: true })
  assert.deepEqual(streamText(shown, 'chunk', '최종 답변'), { content: '최종 답변', draft: false })
  assert.equal(streamText(start, 'chunk', '바로 온 답변').content, '바로 온 답변')
})

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { streamChat } from '../src/api/chatApi.js'
import { mergeTool, interruptTools } from '../src/components/Chat/toolState.js'

test('tool updates replace the pending card and retain terminal results on disconnect', () => {
  let tools = mergeTool([], { id: 'primary', tool: 'none', status: 'selecting' })
  tools = mergeTool(tools, { id: 'primary', tool: 'document_search', status: 'running' })
  assert.equal(tools.length, 1)
  assert.equal(interruptTools(tools)[0].status, 'interrupted')
  tools = mergeTool(tools, { id: 'primary', tool: 'document_search', status: 'not_found' })
  assert.equal(interruptTools(tools)[0].status, 'not_found')
  assert.deepEqual(mergeTool(tools, { id: 'x', tool: 'shell', status: 'ok' }), tools)
})

test('SSE handles split UTF-8, tool, calc and chunk events in order', async t => {
  const source = [
    { type: 'tool', id: 'primary', tool: 'law_lookup', status: 'running' },
    { type: 'tool', id: 'primary', tool: 'law_lookup', status: 'ok', context: '조문 원문' },
    { type: 'chunk', text: '답변' },
    { type: 'calc', tool: 'vat', params: { sales: 100 } },
  ].map(e => 'data: ' + JSON.stringify(e) + '\r\n\r\n').join('') + 'data: [DONE]\r\n\r\n'
  const bytes = new TextEncoder().encode(source)
  const events = []
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += 3) controller.enqueue(bytes.slice(i, i + 3))
      controller.close()
    },
  })))
  await streamChat('질문', 'id', v => events.push(v), () => events.push('done'),
    v => events.push(v.tool), v => events.push(v.status))
  assert.deepEqual(events, ['running', 'ok', '답변', 'vat', 'done'])
})

test('SSE replacement swaps the generated answer with corrected citations', async t => {
  const body = [
    { type: 'chunk', text: '[법률] 소득세법 제101조 - 부당 Lerer계산' },
    { type: 'replace', text: '[법률] 소득세법 제101조 - 양도소득의 부당행위계산' },
  ].map(e => 'data: ' + JSON.stringify(e) + '\n\n').join('') + 'data: [DONE]\n\n'
  t.mock.method(globalThis, 'fetch', async () => new Response(body))
  let answer = ''
  await streamChat('질문', 'id', chunk => { answer += chunk }, () => {}, null, null, null,
    corrected => { answer = corrected })
  assert.equal(answer, '[법률] 소득세법 제101조 - 양도소득의 부당행위계산')
})

test('unexpected EOF never reports successful completion', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('data: {"type":"chunk","text":"일부"}\n\n'))
  let completed = false
  await assert.rejects(streamChat('q', 'id', () => {}, () => { completed = true }), /중단/)
  assert.equal(completed, false)
})

test('generation incomplete event retains partial text but never reports completion', async t => {
  const body = 'data: {"type":"chunk","text":"일부"}\n\n' +
    'data: {"type":"error","code":"generation_incomplete","message":"답변 생성이 중단되었습니다."}\n\n'
  t.mock.method(globalThis, 'fetch', async () => new Response(body))
  const chunks = []
  let completed = false
  await assert.rejects(streamChat('q', 'id', v => chunks.push(v), () => { completed = true }), /중단/)
  assert.deepEqual(chunks, ['일부'])
  assert.equal(completed, false)
})

test('abort signal reaches fetch', async t => {
  const controller = new AbortController()
  controller.abort()
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    assert.equal(options.signal, controller.signal)
    throw new DOMException('aborted', 'AbortError')
  })
  await assert.rejects(streamChat('q', 'id', () => {}, null, null, null, controller.signal), { name: 'AbortError' })
})

test('tool card escapes document markup and exposes only valid actions', async () => {
  const { createServer } = await import('vite')
  const { createElement } = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: Card } = await server.ssrLoadModule('/src/components/Chat/ToolCallCard.jsx')
    const html = renderToStaticMarkup(createElement(Card, {
      tool: { tool: 'document_search', status: 'ok', context: '<img src=x onerror=alert(1)>' },
    }))
    assert.ok(html.includes('&lt;img'))
    assert.ok(!html.includes('<img'))
    assert.ok(html.includes('내 문서 검색') && html.includes('완료'))
    const law = renderToStaticMarkup(createElement(Card, {
      tool: { tool: 'law_lookup', status: 'ok', params: { law_name: '소득세법', article_no: '제55조' } },
      onCitationClick: () => {},
    }))
    assert.ok(law.includes('조문 원문 열기'))
    const failed = renderToStaticMarkup(createElement(Card, {
      tool: { tool: 'law_lookup', status: 'not_found' }, onCitationClick: () => {},
    }))
    assert.ok(!failed.includes('<button'))
    const history = renderToStaticMarkup(createElement(Card, {
      tool: { tool: 'history_lookup', status: 'ok', params: { law_name: '소득세법', article_no: '제1조' } },
      onCitationClick: () => {}, onOpenCalculator: () => {},
    }))
    assert.ok(history.includes('과거 법령·GraphRAG 조회'))
    assert.ok(!history.includes('<button'))
    for (const [error_code, label] of [
      ['history_generation_failed', '답변 생성 실패'],
      ['history_quote_validation_failed', '인용 검증 실패'],
    ]) {
      const failure = renderToStaticMarkup(createElement(Card, {
        tool: { tool: 'history_lookup', status: 'error', error_code,
          retrieval_status: 'ok', context: '조회 성공 / 요약 보류', retryable: true },
        onRetry: () => {},
      }))
      assert.ok(failure.includes(label) && failure.includes('질문 다시 실행'))
      assert.ok(!failure.includes('완료'))
    }
  } finally { await server.close() }
})

test('chat message actions render as labelled icon-only buttons', async () => {
  const { createServer } = await import('vite')
  const { createElement } = await import('react')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { default: MessageBubble } = await server.ssrLoadModule('/src/components/Chat/MessageBubble.jsx')
    const question = renderToStaticMarkup(createElement(MessageBubble, {
      message: { role: 'user', content: '질문' }, onEdit: () => {},
    }))
    const answer = renderToStaticMarkup(createElement(MessageBubble, {
      message: { role: 'assistant', content: '답변', status: 'complete' }, onRegenerate: () => {},
    }))
    assert.match(question, /aria-label="마지막 질문 수정"/)
    assert.match(answer, /aria-label="다시 답변"/)
    assert.match(answer, /aria-label="답변 공유"/)
    assert.doesNotMatch(answer, />↻ 다시 답변</)
  } finally { await server.close() }
})

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

test('unexpected EOF never reports successful completion', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('data: {"type":"chunk","text":"일부"}\n\n'))
  let completed = false
  await assert.rejects(streamChat('q', 'id', () => {}, () => { completed = true }), /중단/)
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
  } finally { await server.close() }
})

// Capture the real React UI with synthetic API data; never contacts a user account.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const path = require('node:path')
const os = require('node:os')
const fs = require('node:fs')

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url())
      let body = {}
      if (url.pathname === '/api/auth/login') body = { user: { id: 'portfolio', email: 'demo@example.test', name: '포트폴리오 시연' } }
      else if (url.pathname === '/api/documents') body = []
      else if (url.pathname === '/api/health/dependencies') body = {
        status: 'ready',
        llm: { status: 'ok', provider: 'ollama', model: 'qwen3.5:9b' },
        embedding: { status: 'ok', provider: 'ollama', model: 'qwen3-embedding:4b' },
      }
      else if (url.pathname === '/api/conversations') body = [{ id: 'demo', title: '법령 근거 확인하기', created_at: '2026-09-07T00:00:00Z', updated_at: '2026-09-07T00:00:00Z' }]
      else if (url.pathname.endsWith('/messages')) body = [
        { role: 'user', content: '소득세법 제55조를 확인하고, 원문도 보여주세요.' },
        { role: 'assistant', content: '## 조회한 근거를 직접 확인하세요\n\n소득세법 제55조를 원문 조회 도구로 확인하는 화면입니다. 아래 **조문 원문 열기**를 누르면 저장된 조문을 옆에서 읽을 수 있습니다.\n\n### 근거 출처\n[법률] 소득세법 제55조\n\n> 포트폴리오용 합성 응답입니다. 실제 세무 상담 결과가 아닙니다.', tools: [
          { type: 'tool', id: 'primary', tool: 'law_lookup', status: 'ok', params: { law_name: '소득세법', article_no: '제55조' }, context: '소득세법 제55조\n조회 완료 · 원문 확인 가능\n※ 포트폴리오 시연용 합성 데이터' },
        ] },
      ]
      else if (url.pathname === '/api/law-articles/lookup') body = {
        law_name: '소득세법', law_type: '법률', article_no: '제55조', article_title: '원문 조회 시연',
        article_text: '[포트폴리오 시연용 합성 본문]\n\n실제 서비스에서는 국가법령정보 API에서 수집해 DB에 저장한 조문 본문을 이 영역에 표시합니다.\n\n사용자는 답변과 근거를 한 화면에서 비교하고, 원문의 적용 조건을 직접 확인할 수 있습니다.\n\n이 캡처는 UI 동작을 보여주기 위한 예시이며, 법령 내용이나 실제 LLM 응답을 재현한 자료가 아닙니다.',
      }
      return route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://127.0.0.1:4173')
    await page.locator('input[type=email]').fill('demo@example.test')
    await page.locator('input[type=password]').fill('synthetic-only')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '조문 원문 열기 →' }).waitFor()
    await page.getByText('AI 연결됨', { exact: false }).waitFor()
    await page.evaluate(() => document.fonts.ready)
    if (await page.getByRole('alert').count()) throw new Error('Unexpected UI alert before capture')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const chat = await page.screenshot({ animations: 'disabled' })
    await page.getByRole('button', { name: '조문 원문 열기 →' }).click()
    await page.getByText('제55조 [원문 조회 시연]', { exact: true }).waitFor()
    const source = await page.screenshot({ animations: 'disabled' })
    if (errors.length) throw new Error(errors.join('\n'))
    // Replace only the two approved assets after both captures succeed.
    const out = fs.mkdtempSync(path.join(os.tmpdir(), 'tax-synthetic-ui-'))
    fs.writeFileSync(path.join(out, 'chat.png'), chat)
    fs.writeFileSync(path.join(out, 'source.png'), source)
    console.log('Synthetic UI checks only (live slide assets preserved): ' + out)
  } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })

// Optional browser smoke: run preview, then PLAYWRIGHT_MODULE=<module path> node tests/tools.browser.cjs.
// API responses are synthetic: no account, document or conversation is written.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } })
    const errors = []
    let calculatorFailure = false
    page.on('pageerror', e => errors.push(e.message))
    const tools = [
      { tool: 'law_lookup', status: 'ok', params: { law_name: '소득세법', article_no: '제55조' }, context: '소득세법 제55조 저장 원문' },
      { tool: 'document_search', status: 'ok', params: { query: '계약' }, context: '계약서.pdf\n<img src=x onerror=alert(1)> 지급일: 매월 말일' },
      { tool: 'income_tax', status: 'ok', params: { income: 50000000 }, context: '세목: 소득세\n계산 결과 예시' },
    ]
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let body = {}
      if (path === '/api/calculator/income-tax') return route.fulfill({
        status: calculatorFailure ? 503 : 200,
        json: calculatorFailure ? { detail: { code: 'missing_tax_data', message: '세율 데이터 확인 필요', retryable: false } }
          : { tax_type: '소득세', steps: [], taxable_income: 0, calculated_tax: 0, final_tax: 0, effective_rate: 0, source_articles: [] },
      })
      if (path === '/api/auth/login') body = { user: { id: 'test', email: 'portfolio@example.test' } }
      else if (path === '/api/documents') body = []
      else if (path === '/api/conversations') body = [
        { id: 'one', title: '도구 UI 검증', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
        { id: 'two', title: '다른 대화', created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
      ]
      else if (path.endsWith('/messages')) body = tools.map((tool, i) => ({
        role: 'assistant', content: '도구 실행 결과 ' + (i + 1), tools: [{ id: 'primary', type: 'tool', ...tool }],
      }))
      else if (path === '/api/law-articles/lookup') body = {
        law_name: '소득세법', article_no: '제55조', article_title: '테스트 조문',
        article_text: '합성 원문', source_url: '', effective_date: '2026-01-01',
      }
      else if (path === '/api/chat/stream') return route.fulfill({
        contentType: 'text/event-stream',
        body: [
          { type: 'tool', id: 'primary', tool: 'document_search', status: 'not_found', context: '관련 자료 없음' },
          { type: 'chunk', text: '관련 문서를 찾지 못했습니다.' },
        ].map(e => 'data: ' + JSON.stringify(e) + '\n\n').join('') + 'data: [DONE]\n\n',
      })
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://127.0.0.1:4173')
    await page.locator('input[type=email]').fill('portfolio@example.test')
    await page.locator('input[type=password]').fill('test-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '조문 원문 열기 →' }).waitFor()
    for (const name of ['법령 원문 조회', '내 문서 검색', '소득세 계산']) {
      assert.equal(await page.getByRole('region', { name }).count(), 1)
    }
    await page.getByRole('region', { name: '내 문서 검색' }).locator('summary').click()
    assert.equal(await page.getByRole('region', { name: '내 문서 검색' }).locator('img').count(), 0)
    await page.getByRole('button', { name: '조문 원문 열기 →' }).click()
    await page.getByText('합성 원문', { exact: true }).waitFor()
    await page.getByRole('button', { name: '닫기', exact: true }).click()
    await page.locator('textarea').fill('내 계약서 찾아줘')
    await page.locator('textarea').press('Enter')
    await page.getByText('자료 없음', { exact: true }).waitFor()
    if (process.env.UI_SCREENSHOT) await page.screenshot({ path: process.env.UI_SCREENSHOT, fullPage: true, animations: 'disabled' })
    await page.getByRole('button', { name: '계산기에서 조건 바꾸기 →' }).click()
    const values = await page.locator('input').evaluateAll(inputs => inputs.map(input => input.value))
    assert.ok(values.some(value => value.replaceAll(',', '') === '5000')) // UI 단위: 만원
    await page.getByRole('button', { name: '계산하기', exact: true }).click()
    await page.getByText('소득세 계산 결과', { exact: true }).waitFor()
    await page.locator('input[type=number]').first().fill('')
    assert.equal(await page.getByText('소득세 계산 결과', { exact: true }).count(), 0)
    await page.getByRole('button', { name: '계산하기', exact: true }).click()
    await page.getByRole('alert').waitFor()
    await page.locator('input[type=number]').first().fill('5000')
    calculatorFailure = true
    await page.getByRole('button', { name: '계산하기', exact: true }).click()
    await page.getByText('세율 데이터 확인 필요', { exact: true }).waitFor()
    assert.equal(await page.getByText('소득세 계산 결과', { exact: true }).count(), 0)
    assert.deepEqual(errors, [])
    console.log('PASS: restored cards, law viewer, escaped document, SSE not_found, calculator prefill, no page errors')
  } finally {
    await browser.close()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })

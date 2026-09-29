// Synthetic display fixtures only. No real chat/account writes.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const content = '**지출 목적과 귀속을 함께 확인하세요.**\n\n질문의 항목별로 확인할 내용을 정리했습니다.\n\n' +
      '## 항목별 검토\n\n| 항목 | 금액 | 확인할 내용 |\n| --- | ---: | --- |\n' +
      '| 출장비 | 800만 원 | 출장 일정과 업무 목적을 대조합니다. |\n' +
      '| 선물비 | 200만 원 | 수령인과 전달 목적을 확인합니다. |\n\n' +
      '### 자료 확인 순서\n\n1. 결제내역을 준비하세요.\n2. 관련 업무 자료와 대조하세요.\n\n' +
      '> **적용 시점:** 해당 연도의 적용 법령은 별도 확인이 필요합니다.'
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let body = {}
      if (path === '/api/auth/login') body = { user: { id: 'display', email: 'display@example.test' } }
      else if (path === '/api/conversations') body = [{ id: 'display', title: '답변 표시 검토' }]
      else if (path.endsWith('/messages')) body = [{ role: 'user', content: '지출 항목별로 확인할 자료를 정리해 주세요.' },
        { role: 'assistant', content, tools: [{ id: 'lookup', tool: 'law_lookup', status: 'ok', context: '표시 테스트 자료' }] }]
      else if (path === '/api/documents') body = []
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3001')
    await page.getByLabel('이메일').fill('display@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('table').waitFor()
    assert.equal(await page.locator('.answer-tools').getAttribute('open'), null)
    assert.equal(await page.locator('.markdown-bubble ol > li').count(), 2)
    assert.equal(await page.locator('.markdown-bubble > p > strong').first().innerText(), '지출 목적과 귀속을 함께 확인하세요.')
    const region = page.getByRole('region', { name: '답변 표', exact: true })
    await region.focus()
    assert.ok(await region.evaluate(el => el === document.activeElement))
    if (process.env.UI_SCREENSHOT) await page.screenshot({ path: process.env.UI_SCREENSHOT, fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '사이드바 접기', exact: true }).first().click()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    assert.ok(await region.evaluate(el => el.scrollWidth > el.clientWidth))
    await region.evaluate(el => { el.scrollLeft = el.scrollWidth })
    assert.ok(await region.evaluate(el => el.scrollLeft > 0))
    await region.evaluate(el => { el.scrollLeft = 0 })
    if (process.env.UI_MOBILE_SCREENSHOT) await page.screenshot({ path: process.env.UI_MOBILE_SCREENSHOT, fullPage: true })
    assert.deepEqual(errors, [])
    console.log('PASS: prose, headings, lists, collapsed tools, semantic table, keyboard focus, mobile scrolling')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

// Render a saved, actually generated result through the production chat UI.
// API interception keeps the check independent of accounts and chat DB writes.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
;(async () => {
  const result = JSON.parse(fs.readFileSync(process.env.UI_FORMULA_JSON, 'utf8'))
  const formula = result.verification.formula_calculation
  assert.ok(formula?.execution, 'Fixture must contain a verified formula calculation')
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let body = {}
      if (path === '/api/auth/login') body = { user: { id: 'formula', email: 'formula@example.test' } }
      else if (path === '/api/conversations') body = [{ id: 'formula', title: '근거 기반 참고 계산 검토' }]
      else if (path.endsWith('/messages')) body = [
        { role: 'user', content: result.question },
        { role: 'assistant', content: result.answer, verification: result.verification,
          tools: [{ id: 'primary', tool: 'formula_calculation', status: 'ok', context: '근거·산식 대조 완료' }] },
      ]
      else if (path === '/api/documents') body = []
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3001')
    await page.getByLabel('이메일').fill('formula@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.locator('.markdown-bubble table').first().waitFor()
    assert.ok((await page.locator('.markdown-bubble').innerText()).includes('참고 계산의 범위와 가정'))
    assert.equal(await page.getByRole('button', { name: /계산기에서/ }).count(), 0)
    assert.equal(await page.locator('.answer-tools').getAttribute('open'), null)
    await page.locator('.verification-panel > summary').click()
    await page.getByText('계산에 사용한 값과 산식', { exact: true }).click()
    assert.equal(await page.locator('.formula-details ol > li').count(), formula.execution.steps.length)
    assert.ok((await page.locator('.formula-details').innerText()).includes('사용자 제공'))
    assert.ok((await page.locator('.formula-details').innerText()).includes('원문 수치'))
    assert.equal(await page.locator('.verification-sources details').count(), result.verification.citations.length)
    await page.locator('.verification-panel > summary').click()
    await page.locator('.markdown-bubble').evaluate(el => el.scrollIntoView({ block: 'start' }))
    if (process.env.UI_SCREENSHOT) await page.screenshot({ path: process.env.UI_SCREENSHOT, fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '사이드바 접기', exact: true }).first().click()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    assert.deepEqual(errors, [])
    console.log('PASS: actual formula answer, assumptions, expandable trace, provenance, source snapshots, mobile width')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

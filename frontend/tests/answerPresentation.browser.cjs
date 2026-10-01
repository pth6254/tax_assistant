// Synthetic display fixtures only. No real chat/account writes.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const fixture = process.env.UI_ANSWER_JSON && JSON.parse(fs.readFileSync(process.env.UI_ANSWER_JSON, 'utf8'))
    const content = fixture?.answer || '## 핵심 판단\n\n**지출 목적과 귀속을 함께 확인하세요.**\n\n' +
      '## 항목별 검토\n\n| 항목 | 금액 | 확인할 내용 |\n| --- | ---: | --- |\n' +
      '| 출장비 | 800만 원 | 출장 일정과 업무 목적을 대조합니다. |\n' +
      '| 선물비 | 200만 원 | 수령인과 전달 목적을 확인합니다. |\n\n' +
      '## 실무 확인 사항\n\n1. 결제내역을 준비하세요.\n2. 관련 업무 자료와 대조하세요.\n\n' +
      '## 추가 확인이 필요한 부분\n\n- 거래 시점을 확인하세요.\n\n' +
      '**확인한 근거**\n\n- [법률] 시험법 제1조\n\n' +
      '> **적용 시점:** 해당 연도의 적용 법령은 별도 확인이 필요합니다.'
    const verification = fixture?.verification || { status: 'limited', note: '화면 표시용 합성 자료입니다.',
      checks: { citation: 'checked', calculation: 'not_applicable', legal_application: 'not_assessed' },
      plan: { issues: [{ id: 'I1', subject: 'H', law: '법인세법' }] },
      claims: [{ id: 'C1', issue_id: 'I1', released: true }],
      citations: [{ evidence_id: 'display-source', label: '법률', law_name: '시험법', reference: '제1조',
        effective_from: '2025-01-01', text: '제1조\n① 표시 테스트입니다.' }] }
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let body = {}
      if (path.startsWith('/api/health/')) return route.continue() // Read-only actual dependency status.
      if (path === '/api/auth/login') body = { user: { id: 'display', email: 'display@example.test' } }
      else if (path === '/api/conversations') body = [{ id: 'display', title: fixture ? '세무 검토 답변 예시' : '답변 표시 검토' }]
      else if (path.endsWith('/messages')) body = [{ role: 'user', content: fixture?.question || '지출 항목별로 확인할 자료를 정리해 주세요.' },
        { role: 'assistant', content, verification,
          tools: [{ id: 'lookup', tool: 'law_lookup', status: 'ok', context: '표시 테스트 자료' }] }]
      else if (path === '/api/documents') body = []
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3001')
    await page.getByLabel('이메일').fill('display@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.locator('.markdown-bubble .answer-conclusion').waitFor()
    assert.equal(await page.locator('.answer-tools').getAttribute('open'), null)
    assert.equal(await page.locator('.answer-conclusion .answer-section-title').innerText(), '핵심 판단')
    assert.ok(await page.locator('.answer-sources button.citation-link').count() > 0)
    if (!fixture) {
      assert.equal(await page.locator('.markdown-bubble ol > li').count(), 2)
      assert.equal(await page.locator('.answer-limits').count(), 1)
      assert.equal(await page.locator('.answer-conclusion > p > strong').innerText(), '지출 목적과 귀속을 함께 확인하세요.')
    }
    const region = page.getByRole('region', { name: '답변 표', exact: true }).first()
    if (await region.count()) {
      await region.focus()
      assert.ok(await region.evaluate(el => el === document.activeElement))
    }
    const panel = page.locator('.verification-panel')
    assert.equal(await panel.getAttribute('open'), null)
    assert.ok((await panel.locator(':scope > summary').innerText()).includes(`근거 ${verification.citations.length}건`))
    await panel.locator(':scope > summary').click()
    assert.equal(await panel.locator('.verification-sources details').count(), verification.citations.length)
    assert.equal(await panel.getByText('계산기를 사용하지 않았습니다.', { exact: true }).count(), 0)
    await panel.locator(':scope > summary').click()
    await page.locator('.assistant-message').evaluate(el => el.scrollIntoView({ block: 'start' }))
    if (process.env.UI_SCREENSHOT) await page.screenshot({ path: process.env.UI_SCREENSHOT, fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '사이드바 접기', exact: true }).first().click()
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    if (await region.count()) {
      assert.ok(await region.evaluate(el => el.scrollWidth > el.clientWidth))
      await region.evaluate(el => { el.scrollLeft = el.scrollWidth })
      assert.ok(await region.evaluate(el => el.scrollLeft > 0))
      await region.evaluate(el => { el.scrollLeft = 0 })
    }
    if (process.env.UI_MOBILE_SCREENSHOT) await page.screenshot({ path: process.env.UI_MOBILE_SCREENSHOT, fullPage: true })
    assert.deepEqual(errors, [])
    console.log('PASS: core assessment, section hierarchy, actionable checks, linked sources, scope panel, mobile width')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

// Synthetic API browser regression; never writes real user data.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const path = require('node:path')
const os = require('node:os')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    let failHistory = true, requests = 0, release, deleted = false
    const held = new Promise(resolve => { release = resolve })
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()), p = url.pathname
      let body = {}
      if (p === '/api/auth/login') body = { user: { id: 'demo', email: 'demo@example.test' } }
      else if (p === '/api/conversations') body = [{ id: 'one', title: '근거를 확인하는 세무 상담' }]
      else if (p.endsWith('/messages')) {
        if (failHistory) return route.fulfill({ status: 503, json: { detail: '대화 조회 테스트 오류' } })
        body = [{ role: 'user', content: '소득세법 제55조 제1항을 확인해주세요' }, { role: 'assistant', content: '## 확인한 근거\n[법률] 소득세법 제55조 제1항\n\n답변과 원문의 적용 조건을 함께 확인하세요.\n\n<script>window.xss = true</script><img src=x onerror="window.xss=true">' }]
      } else if (p === '/api/health/dependencies') body = { llm: { status: 'ok', provider: 'ollama', model: 'qwen3.5:9b' }, embedding: { status: 'ok', provider: 'ollama', model: 'qwen3-embedding:4b' } }
      else if (p === '/api/law-articles/lookup') body = { law_name: '소득세법', article_no: '제55조', article_title: '합성 조회 예시', article_text: '① 테스트용 첫째 항\n② 테스트용 둘째 항', target: { exists: true, text: '① 테스트용 첫째 항' } }
      else if (p === '/api/documents') body = deleted ? [] : [{ filename: '검증.pdf', category: '기타', chunk_count: 2, search_ready: true }]
      else if (p === '/api/documents/검증.pdf' || decodeURIComponent(p) === '/api/documents/검증.pdf') { deleted = true; body = { status: 'ok' } }
      else if (p === '/api/chat/stream') { requests++; await held; return route.fulfill({ contentType: 'text/event-stream', body: 'data: [DONE]\n\n' }).catch(() => {}) }
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://127.0.0.1:4173')
    await page.getByLabel('이메일').fill('demo@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('alert').waitFor()
    assert.equal(await page.getByRole('button', { name: '질문 전송' }).isDisabled(), true)
    failHistory = false
    await page.getByRole('button', { name: '다시 시도', exact: true }).click()
    const citation = page.locator('.citation-link').first()
    await citation.waitFor()
    await citation.focus(); await page.keyboard.press('Enter')
    await page.locator('.source-text mark').waitFor()
    assert.equal(await page.locator('.source-text mark').innerText(), '① 테스트용 첫째 항')
    assert.equal(await page.evaluate(() => !!window.xss), false)
    await page.screenshot({ path: path.join(os.tmpdir(), 'tax-refactor-desktop.png'), animations: 'disabled' })
    await page.keyboard.press('Escape')
    assert.equal(await page.locator('.source-panel').count(), 0)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '사이드바 접기' }).first().click()
    await citation.click()
    await page.locator('.source-text mark').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.getByRole('button', { name: '닫기', exact: true }).focus()
    await page.keyboard.press('Shift+Tab')
    assert.equal(await page.locator('.source-panel').evaluate(el => el.contains(document.activeElement)), true)
    await page.screenshot({ path: path.join(os.tmpdir(), 'tax-refactor-mobile-source.png'), animations: 'disabled' })
    await page.keyboard.press('Escape')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.getByRole('button', { name: '사이드바 펼치기' }).first().click()
    const input = page.locator('textarea')
    await input.fill('한글 입력 검증')
    await input.dispatchEvent('compositionstart')
    await input.press('Enter')
    assert.equal(requests, 0)
    await input.dispatchEvent('compositionend')
    await input.press('Enter')
    await page.getByRole('button', { name: '답변 생성 중지' }).waitFor()
    await page.getByRole('button', { name: '답변 생성 중지' }).click()
    assert.equal(await input.isDisabled(), false)
    release()
    await page.getByRole('button', { name: '내 문서', exact: true }).click()
    await page.getByText('검색 준비 완료', { exact: true }).waitFor()
    page.once('dialog', d => d.accept())
    await page.getByRole('button', { name: '검증.pdf 삭제' }).click()
    await page.getByText('아직 저장된 문서가 없습니다.').waitFor()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '사이드바 접기' }).first().click()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: path.join(os.tmpdir(), 'tax-refactor-mobile.png'), animations: 'disabled' })
    assert.deepEqual(errors, [])
    console.log('PASS: history retry, keyboard citation, target highlight, XSS, IME, stop, document deletion, mobile width')
  } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })

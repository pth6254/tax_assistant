// Real local service capture. Creates only its own temporary account and removes it afterwards.
// No route interception, response substitution, credential persistence or answer editing.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const { randomBytes } = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')

;(async () => {
  const base = process.env.UI_TEST_URL || 'http://localhost:3000'
  if (!['localhost', '127.0.0.1'].includes(new URL(base).hostname)) throw new Error('Local service only')
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await context.newPage()
  const email = `portfolio-${Date.now()}@example.com`, password = randomBytes(24).toString('hex')
  let created = false, signedIn = false
  const query = '소득세법 제50조 제1항의 기본공제 대상이 누구인지, 저장된 조문을 근거로 3문장으로 설명해 주세요.'
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  try {
    const health = await context.request.get(base + '/api/health/dependencies')
    assert.equal(health.status(), 200)
    const status = await health.json()
    assert.equal(status.status, 'ready')
    const signup = await context.request.post(base + '/api/auth/signup', { data: { email, password } })
    assert.equal(signup.status(), 201, 'Temporary account creation failed')
    created = true
    await page.goto(base)
    await page.locator('input[type=email]').fill(email)
    await page.locator('input[type=password]').fill(password)
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '새 대화 시작' }).waitFor()
    signedIn = true
    await page.getByRole('button', { name: '새 대화 시작' }).click()
    await page.locator('textarea').waitFor()
    await page.locator('textarea').fill(query)
    const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/chat/stream'), { timeout: 240000 })
    const start = Date.now()
    await page.getByRole('button', { name: '질문 전송' }).click()
    console.log('Submitted live question; waiting for real model response.')
    const response = await responsePromise
    assert.equal(response.status(), 200)
    await page.getByRole('button', { name: '답변 생성 중지' }).waitFor({ state: 'hidden', timeout: 240000 })
    assert.equal(await page.getByRole('alert').count(), 0, 'UI shows an error')
    const answer = await page.locator('.assistant-message .markdown-bubble').last().innerText()
    assert.ok(answer.length > 40, 'Answer is empty or too short')
    const conversations = await (await context.request.get(base + '/api/conversations')).json()
    assert.equal(conversations.length, 1)
    const saved = await (await context.request.get(base + '/api/conversations/' + conversations[0].id + '/messages')).json()
    assert.ok(saved.some(m => m.role === 'assistant' && m.content.length > 40), 'No persisted assistant answer')
    assert.equal(await page.locator('.generation-status').count(), 0)
    const citations = page.locator('.citation-link')
    assert.ok(await citations.count() > 0, 'No citation action to capture')
    await page.evaluate(() => document.fonts.ready)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.locator('.messages-scroll').evaluate(el => { el.scrollTop = 0 })
    const chat = await page.screenshot({ animations: 'disabled' })
    const sourceResponse = page.waitForResponse(r => r.url().includes('/api/law-articles/lookup'))
    await citations.first().click()
    const lawResponse = await sourceResponse
    assert.equal(lawResponse.status(), 200)
    const law = await lawResponse.json()
    await page.locator('.source-text').waitFor()
    assert.ok(law.article_text?.length > 40)
    await page.locator('.messages-scroll').evaluate(el => { el.scrollTop = 0 })
    const source = await page.screenshot({ animations: 'disabled' })
    assert.deepEqual(errors, [])
    fs.writeFileSync(path.join(__dirname, 'assets/chat.png'), chat)
    fs.writeFileSync(path.join(__dirname, 'assets/source.png'), source)
    const evidence = { captured_at: new Date().toISOString(), mode: 'live-local-service', query, answer,
      elapsed_ms: Date.now() - start, llm: status.llm?.model, embedding: status.embedding?.model,
      ui_generation_completed: true, persisted_answer_verified: true, law: { name: law.law_name, article: law.article_no, effective_date: law.effective_date },
      note: 'Real service output, not a legal accuracy certification. Temporary account is deleted after capture.' }
    fs.writeFileSync(path.join(__dirname, 'live-capture.json'), JSON.stringify(evidence, null, 2) + '\n')
    console.log(JSON.stringify(evidence, null, 2))
  } finally {
    if (created) {
      if (!signedIn) await context.request.post(base + '/api/auth/login', { data: { email, password } })
      const removed = await context.request.delete(base + '/api/users/me', { data: { password } })
      console.log('Temporary account cleanup HTTP ' + removed.status())
      if (!removed.ok()) { console.error('Cleanup failed for temporary account: ' + email); process.exitCode = 1 }
    }
    await browser.close()
  }
})().catch(e => { console.error(e.message); process.exitCode = 1 })

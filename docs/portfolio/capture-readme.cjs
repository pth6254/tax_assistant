// README screenshots: real answers the service produced, shown by the current frontend.
// readme-fixtures/analysis.json is a stored conversation (regenerated 2026-11-07); calculation.json came from
// one chat turn run through chat_service without storing it (that question needs no model call). /api/** is
// answered from those files, so nothing is written to accounts or chats and no model is called.
// Run from the repository root with the Docker frontend on localhost:3001:
//   PLAYWRIGHT_MODULE=./frontend/node_modules/playwright node docs/portfolio/capture-readme.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const fs = require('node:fs')
const path = require('node:path')

const here = __dirname
const out = path.join(here, '..', 'images')
const base = process.env.UI_TEST_URL || 'http://localhost:3001'
const load = name => JSON.parse(fs.readFileSync(path.join(here, 'readme-fixtures', name), 'utf8'))

async function open(browser, messages, title) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.startsWith('/api/health/')) return route.continue()
    let body = {}
    if (url.pathname === '/api/auth/login') body = { user: { id: 'readme', email: 'readme@example.test' } }
    else if (url.pathname === '/api/conversations') body = [{ id: 'readme', title }]
    else if (url.pathname.endsWith('/messages')) body = messages
    else if (url.pathname === '/api/documents') body = []
    await route.fulfill({ json: body })
  })
  await page.goto(base)
  await page.getByLabel('이메일').fill('readme@example.test')
  await page.locator('input[type=password]').fill('synthetic-password')
  await page.getByRole('button', { name: '로그인', exact: true }).last().click()
  await page.locator('.assistant-message .markdown-bubble').last().waitFor()
  return { context, page, errors }
}

async function shot(page, name) {
  const file = path.join(out, name)
  await page.screenshot({ path: file })
  console.log('saved', path.relative(process.cwd(), file))
}

;(async () => {
  fs.mkdirSync(out, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    // 1. An evidence-based analysis answer: the core judgement and the per-item review.
    const analysis = load('analysis.json')
    let { context, page, errors } = await open(browser, analysis, 'H건설 컨설팅 비용 세무 처리')
    await page.locator('.user-message').last().evaluate(el => el.scrollIntoView({ block: 'start' }))
    await shot(page, 'chat-analysis.png')
    // 2. The same answer's evidence panel: each source with the passage the answer quoted and its dates.
    const panel = page.locator('.verification-panel').last()
    await panel.locator(':scope > summary').click()
    await panel.locator('.verification-sources details > summary').first().click()
    await panel.evaluate(el => el.scrollIntoView({ block: 'start' }))
    await shot(page, 'chat-evidence.png')
    if (errors.length) throw new Error(errors.join('\n'))
    await context.close();
    // 3. A calculation answer: the deterministic calculator's steps and the assumptions it stated.
    ({ context, page, errors } = await open(browser, load('calculation.json'), '1세대 1주택 양도소득세'))
    await page.locator('.user-message').last().evaluate(el => el.scrollIntoView({ block: 'start' }))
    await shot(page, 'chat-calculation.png')
    if (errors.length) throw new Error(errors.join('\n'))
    await context.close()
  } finally {
    await browser.close()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })

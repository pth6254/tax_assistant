// Synthetic API only: checks profile form behavior and card visibility at desktop/mobile sizes.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const path = require('node:path')
const os = require('node:os')

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const updates = [], passwordChanges = [], errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/**', async route => {
      const request = route.request(), endpoint = new URL(request.url()).pathname
      let body = {}
      if (endpoint === '/api/auth/login') body = { user: { id: 'demo', email: 'demo@example.test' } }
      else if (endpoint === '/api/conversations' || endpoint === '/api/documents') body = []
      else if (endpoint === '/api/users/me' && request.method() === 'GET') {
        body = { email: 'demo@example.test', name: '', phone: '', business_type: '개인_일반과세' }
      } else if (endpoint === '/api/users/me' && request.method() === 'PATCH') {
        updates.push(request.postDataJSON()); body = { status: 'ok' }
      } else if (endpoint === '/api/users/me/password' && request.method() === 'PATCH') {
        passwordChanges.push(request.postDataJSON()); body = { status: 'ok' }
      }
      await route.fulfill({ json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3002')
    await page.getByLabel('이메일').fill('demo@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '내 정보', exact: true }).click()
    await page.getByRole('heading', { name: '프로필 정보' }).waitFor()

    const verifyLayout = async label => {
      const layout = await page.locator('.profile-scroll').evaluate(scroller => ({
        scrolls: scroller.scrollHeight > scroller.clientHeight,
        clippedCards: [...scroller.querySelectorAll('.profile-card')].filter(card => card.scrollHeight > card.clientHeight + 1).length,
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
      }))
      assert.equal(layout.scrolls, true, `${label}: profile content should scroll`)
      assert.equal(layout.clippedCards, 0, `${label}: card content should not be clipped`)
      assert.equal(layout.horizontalOverflow, false, `${label}: no horizontal overflow`)
    }

    await verifyLayout('desktop')
    const headerPositions = await page.locator('.profile-header').evaluate(header => ({
      iconRight: header.querySelector('svg').getBoundingClientRect().right,
      titleLeft: header.querySelector('h1').getBoundingClientRect().left,
    }))
    assert.ok(headerPositions.titleLeft - headerPositions.iconRight < 24, 'profile title should stay next to its icon')
    await page.screenshot({ path: path.join(os.tmpdir(), 'tax-profile-desktop.png'), animations: 'disabled' })
    await page.getByLabel('이름', { exact: true }).fill('테스트')
    await page.getByLabel('전화번호').fill('010-0000-0000')
    await page.getByLabel(/사업자 유형/).selectOption('개인_간이과세')
    await page.getByRole('button', { name: '저장', exact: true }).click()
    await page.getByText('저장되었습니다.').waitFor()
    assert.deepEqual(updates, [{ name: '테스트', phone: '010-0000-0000', business_type: '개인_간이과세' }])

    await page.getByLabel('현재 비밀번호').fill('old-password')
    await page.getByLabel('새 비밀번호', { exact: false }).first().fill('new-password')
    await page.getByLabel('새 비밀번호 확인').fill('new-password')
    await page.getByRole('button', { name: '비밀번호 변경', exact: true }).click()
    await page.getByText('비밀번호가 변경되었습니다.').waitFor()
    assert.equal(passwordChanges.length, 1)

    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.sidebar').getByRole('button', { name: '사이드바 접기' }).click()
    await verifyLayout('mobile')
    await page.screenshot({ path: path.join(os.tmpdir(), 'tax-profile-mobile.png'), animations: 'disabled' })
    assert.deepEqual(errors, [])
    console.log('profile UI: desktop/mobile layout, profile save, password change passed')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

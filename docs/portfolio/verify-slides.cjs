// Local, offline deck QA. Generated screenshots/reports go to a temporary directory.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const { pathToFileURL } = require('node:url')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const assert = require('node:assert/strict')

;(async () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'tax-portfolio-qa-'))
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const problems = []
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 958 } })
    page.on('pageerror', e => problems.push(e.message))
    page.on('request', r => { if (/^https?:/.test(r.url())) problems.push(`Unexpected network: ${r.url()}`) })
    await page.goto(pathToFileURL(path.join(__dirname, process.env.DECK_FILE || 'interview.html')).href)
    await page.waitForFunction(() => [...document.querySelectorAll('#demo-image')].every(i => i.complete && i.naturalWidth > 0))
    for (let i = 0; i < 5; i++) {
      await page.evaluate(n => show(n), i)
      const overflow = await page.locator('.slide:not([hidden])').evaluate(slide => {
        const footerTop = slide.querySelector('.footer').getBoundingClientRect().top
        return [...slide.querySelectorAll('h1,h2,h3,p,td,th,li,dl,.runtime,figure,.metrics,.regression')].flatMap(el => {
          const r = el.getBoundingClientRect(), box = slide.getBoundingClientRect()
          const issue = r.left < box.left || r.right > box.right || r.bottom > footerTop - 5 || el.scrollWidth > el.clientWidth + 3
          return issue ? [{ tag: el.tagName, text: el.textContent.slice(0,65), bottom: r.bottom, footerTop, horizontal: el.scrollWidth > el.clientWidth + 3 }] : []
        })
      })
      if (overflow.length) problems.push({ slide: i + 1, overflow })
      await page.locator('.slide:not([hidden])').screenshot({ path: path.join(out, `slide-${i + 1}.png`) })
    }
    await page.keyboard.press('Home')
    assert.equal(await page.locator('#counter').innerText(), '1 / 5')
    await page.keyboard.press('ArrowRight')
    assert.equal(await page.locator('#counter').innerText(), '2 / 5')
    await page.locator('[data-screen=chat]').click()
    assert.equal(await page.locator('[data-screen=chat]').getAttribute('aria-pressed'), 'true')
    await page.waitForFunction(() => document.querySelector('#demo-image').complete && document.querySelector('#demo-image').naturalWidth > 0)
    await page.locator('#zoom-image').click()
    assert.equal(await page.locator('#image-dialog').evaluate(d => d.open), true)
    await page.keyboard.press('Escape')
    await page.locator('#sources').click()
    assert.equal(await page.locator('#source-dialog').evaluate(d => d.open), true)
    await page.keyboard.press('Escape')
    await page.locator('[data-screen=source]').click()
    for (const viewport of [{ width:1366, height:768 }, { width:390, height:844 }]) {
      await page.setViewportSize(viewport)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    }
    await page.setViewportSize({ width:1600, height:958 })
    await page.emulateMedia({ media:'print' })
    assert.equal(await page.locator('.slide:visible').count(), 5)
    await page.pdf({ path:path.join(out, 'print-check.pdf'), preferCSSPageSize:true, printBackground:true })
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify({ problems }, null, 2))
    console.log(JSON.stringify({ output:out, problems }, null, 2))
    if (problems.length) process.exitCode = 1
  } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })

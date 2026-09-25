// Synthetic API only: editing forks; regeneration versions the same conversation.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage()
    const errors = [], forks = [], streams = [], regenerations = [], selections = []
    let completed = false
    let selectedVersion = 1
    page.on('pageerror', e => errors.push(e.message))
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'share', { value: undefined, configurable: true })
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: async text => { window.__sharedAnswer = text } }, configurable: true,
      })
    })
    await page.route('**/api/**', async route => {
      const p = new URL(route.request().url()).pathname
      let body = {}
      if (p === '/api/auth/login') body = { user: { id:'demo', email:'demo@example.test' } }
      else if (p === '/api/conversations') body = [{id:'one',title:'Original'}, ...forks.map((_,i)=>({id:'fork'+i,title:'Revision'}))]
      else if (p.endsWith('/revise')) {
        const input = route.request().postDataJSON()
        forks.push(input); completed = false; selectedVersion = 1
        body = {id:'fork'+(forks.length-1),query:input.query || 'Original question',original_id:'one'}
      } else if (p.endsWith('/messages')) body = p.includes('/one/') || completed ? [
        {message_id:1,role:'user',content:completed ? 'Edited question' : 'Original question'},
        {message_id:2,role:'assistant',content:completed && selectedVersion === 2 ? 'Regenerated answer' : completed ? 'New answer' : 'Original answer',
          answer_version:selectedVersion, answer_version_count:regenerations.length ? 2 : 1}] : []
      else if (p === '/api/chat/stream') {
        streams.push(route.request().postDataJSON()); completed=true
        return route.fulfill({contentType:'text/event-stream',body:'data: {"type":"chunk","text":"New answer"}\n\ndata: [DONE]\n\n'})
      } else if (p.endsWith('/regenerate')) {
        regenerations.push(route.request().postDataJSON()); selectedVersion = 2
        return route.fulfill({contentType:'text/event-stream',body:'data: {"type":"chunk","text":"Regenerated answer"}\n\ndata: [DONE]\n\n'})
      } else if (p.endsWith('/version')) {
        const input = route.request().postDataJSON()
        selections.push(input); selectedVersion = input.version
        body = {version:selectedVersion}
      } else if (p === '/api/documents') body = []
      await route.fulfill({json:body})
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3002')
    await page.getByLabel('이메일').fill('demo@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button',{name:'로그인',exact:true}).last().click()
    const editButton = page.getByRole('button',{name:'마지막 질문 수정'})
    assert.equal(await editButton.innerText(), '')
    await editButton.click()
    await page.getByLabel('질문 수정',{exact:true}).fill('Edited question')
    await page.getByRole('button',{name:'수정 후 보내기'}).click()
    await page.getByText('New answer',{exact:true}).waitFor()
    const regenerateButton = page.getByRole('button',{name:'다시 답변',exact:true})
    assert.equal(await regenerateButton.innerText(), '')
    await regenerateButton.click()
    await page.waitForFunction(() => document.querySelectorAll('.question-bubble').length === 1)
    await page.getByRole('button',{name:'다시 답변',exact:true}).waitFor()
    await page.getByText('Regenerated answer',{exact:true}).waitFor()
    await page.getByRole('button',{name:'이전 답변 버전'}).click()
    await page.getByText('New answer',{exact:true}).waitFor()
    await page.getByRole('button',{name:'다음 답변 버전'}).click()
    await page.getByText('Regenerated answer',{exact:true}).waitFor()
    const shareButton = page.getByRole('button',{name:'답변 공유'}).last()
    assert.equal(await shareButton.innerText(), '')
    await shareButton.click()
    await page.getByText('답변을 복사했습니다.').waitFor()
    assert.equal(await page.evaluate(() => window.__sharedAnswer), 'Regenerated answer')
    assert.equal(forks.length,1)
    assert.equal(forks[0].query,'Edited question')
    assert.equal(regenerations.length,1)
    assert.deepEqual(regenerations[0],{expected_message_id:2,expected_version:1})
    assert.equal(streams[0].conversation_id,'fork0')
    assert.equal(selections.length,2)
    assert.deepEqual(errors,[])
    console.log('revision UI: edit fork, same-conversation regeneration and version switching passed')
  } finally { await browser.close() }
})().catch(e=>{console.error(e);process.exitCode=1})

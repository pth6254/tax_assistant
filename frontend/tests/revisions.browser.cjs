// Synthetic API only: verifies visible revision controls and branch routing.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage()
    const errors = [], forks = [], streams = []
    let completed = false
    page.on('pageerror', e => errors.push(e.message))
    await page.route('**/api/**', async route => {
      const p = new URL(route.request().url()).pathname
      let body = {}
      if (p === '/api/auth/login') body = { user: { id:'demo', email:'demo@example.test' } }
      else if (p === '/api/conversations') body = [{id:'one',title:'Original'}, ...forks.map((_,i)=>({id:'fork'+i,title:'Revision'}))]
      else if (p.endsWith('/revise')) {
        const input = route.request().postDataJSON()
        forks.push(input); completed = false
        body = {id:'fork'+(forks.length-1),query:input.query || 'Original question',original_id:'one'}
      } else if (p.endsWith('/messages')) body = p.includes('/one/') || completed ? [
        {message_id:1,role:'user',content:completed ? streams.at(-1).query : 'Original question'},
        {message_id:2,role:'assistant',content:completed ? 'New answer' : 'Original answer'}] : []
      else if (p === '/api/chat/stream') {
        streams.push(route.request().postDataJSON()); completed=true
        return route.fulfill({contentType:'text/event-stream',body:'data: {"type":"chunk","text":"New answer"}\n\ndata: [DONE]\n\n'})
      } else if (p === '/api/documents') body = []
      await route.fulfill({json:body})
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3002')
    await page.getByLabel('이메일').fill('demo@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button',{name:'로그인',exact:true}).last().click()
    await page.getByRole('button',{name:'마지막 질문 수정'}).click()
    await page.getByLabel('질문 수정',{exact:true}).fill('Edited question')
    await page.getByRole('button',{name:'수정 후 보내기'}).click()
    await page.getByText('New answer',{exact:true}).waitFor()
    await page.getByRole('button',{name:'↻ 다시 답변',exact:true}).click()
    await page.waitForFunction(() => document.querySelectorAll('.question-bubble').length === 1)
    await page.getByRole('button',{name:'↻ 다시 답변',exact:true}).waitFor()
    assert.equal(forks.length,2)
    assert.equal(forks[0].query,'Edited question')
    assert.equal(forks[1].query,undefined)
    assert.equal(streams[0].conversation_id,'fork0')
    assert.equal(streams[1].conversation_id,'fork1')
    assert.deepEqual(errors,[])
    console.log('revision UI: edit, regenerate, branch routing passed')
  } finally { await browser.close() }
})().catch(e=>{console.error(e);process.exitCode=1})

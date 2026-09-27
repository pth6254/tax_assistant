// Synthetic alternate-tax workflow; no user or DB data is written.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1300, height: 900 } })
    const errors = [], facts = {}, docs = {}
    let current, result
    const fields = [
      ['gift_amount', '증여재산가액은 얼마인가요?', 'amount', null],
      ['relation', '증여자와의 관계는 무엇인가요?', 'choice', ['배우자', '직계존비속', '기타친족', '기타']],
      ['is_minor', '수증자가 미성년자인가요?', 'boolean', null],
      ['prior_gifts_10y', '같은 증여자에게서 10년 내 받은 증여액은 얼마인가요?', 'amount', null],
    ]
    const detail = () => ({ ...current, calculation: result, facts: { ...facts },
      questions: fields.map(([key, question, type, options]) => ({ key, question, type, options,
        unit: type === 'amount' ? '원' : null, value: facts[key] ?? null, answered: facts[key] != null })),
      checklist: [['gift_proof', '증여재산 자료'], ['family_proof', '관계 확인 자료'],
        ['prior_gift_proof', '과거 증여 자료']].map(([key, title]) => ({ key, title, prompt: '자료 확인',
          needed: true, status: docs[key]?.status || 'pending' })),
    })
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname
      let body = {}
      if (path === '/api/auth/login') body = { user: { id: 'synthetic-user', email: 'gift@example.test' } }
      else if (path === '/api/conversations' || path === '/api/documents') body = []
      else if (path === '/api/consultation-cases' && req.method() === 'GET') body = current
        ? [{ id: current.id, kind: 'gift', kind_label: '증여세', title: current.title, tax_year: current.tax_year,
          answered: Object.keys(facts).length, question_count: 4, has_calculation: !!result }] : []
      else if (path === '/api/consultation-cases' && req.method() === 'POST') {
        const input = JSON.parse(req.postData())
        assert.equal(input.kind, 'gift')
        current = { ...input, id: 'gift-case', kind_label: '증여세', conversation_id: 'gift-conversation', has_chat: false,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
        body = detail()
      } else if (path === '/api/consultation-cases/gift-case' && req.method() === 'GET') body = detail()
      else if (path === '/api/consultation-cases/gift-case/scenarios' && req.method() === 'GET') body = []
      else if (path.endsWith('/facts')) { Object.assign(facts, JSON.parse(req.postData())); body = detail() }
      else if (path.endsWith('/calculate')) {
        result = { tax_year: current.tax_year, reference_date: current.reference_date,
          calculated_at: new Date().toISOString(), result: { tax_type: '증여세', steps: [],
            taxable_income: 100000, calculated_tax: 10000, final_tax: 9700,
            effective_rate: 0.097, source_articles: [],
            basis: { queried_on: current.reference_date, effective_dates: ['2024-01-01'] } } }
        body = detail()
      }
      await route.fulfill({ status: path === '/api/consultation-cases' && req.method() === 'POST' ? 201 : 200, json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3001')
    await page.getByLabel('이메일').fill('gift@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '상담 작업', exact: true }).click()
    await page.getByRole('button', { name: '새 상담' }).click()
    await page.getByLabel('세목').selectOption('gift')
    await page.getByRole('textbox', { name: '궁금한 내용' }).fill('증여세 참고 계산이 궁금합니다.')
    await page.getByRole('button', { name: '상담 만들기' }).click()
    for (const [kind, answer] of [['number', '10000'], ['select', '직계존비속'],
      ['select', 'false'], ['number', '0']]) {
      const field = page.locator('#case-next-answer')
      if (kind === 'select') await field.selectOption(answer)
      else await field.fill(answer)
      await page.getByRole('button', { name: '저장하고 다음 질문' }).click()
    }
    await page.getByText('계산에 필요한 조건을 모두 확인했습니다.').waitFor()
    assert.equal(facts.is_minor, false)
    await page.getByRole('button', { name: '증여세 계산하기' }).click()
    await page.getByText('9,700원', { exact: false }).first().waitFor()
    assert.deepEqual(errors, [])
    console.log('PASS: gift consultation choices, explicit false, zero and saved calculation')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

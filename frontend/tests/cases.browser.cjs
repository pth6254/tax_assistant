// Synthetic browser flow. All API requests are intercepted; no user data is written.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')

const fields = [
  ['income', '해당 귀속연도의 총수입금액은 얼마인가요?', '원'],
  ['expense', '필요경비는 얼마인가요? 없다면 0원을 입력해 주세요.', '원'],
  ['personal_deduction_count', '기본공제 대상 인원은 본인을 포함해 몇 명인가요?', '명'],
  ['other_deductions', '기타 소득공제 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', '원'],
]

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1300, height: 900 } })
    const errors = [], facts = {}, docs = {}, list = []
    let current = null, calculation = null
    const detail = () => ({ ...current, facts: { ...facts }, calculation, checklist: [
      ['income_proof', '수입금액 확인 자료'], ['expense_proof', '필요경비 확인 자료'], ['deduction_proof', '공제 확인 자료'],
    ].map(([key, title]) => ({ key, title, prompt: '자료 확인', needed: true, status: docs[key]?.status || 'pending', filename: docs[key]?.filename, note: docs[key]?.note })),
      questions: fields.map(([key, question, unit]) => ({ key, question, unit, answered: facts[key] != null, value: facts[key] ?? null })),
      next_question: fields.find(([key]) => facts[key] == null)?.[1] || null })
    page.on('pageerror', e => errors.push(e.message))
    await page.route('**/api/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname
      let body = {}
      if (path === '/api/auth/login') body = { user: { id: 'synthetic-user', email: 'case@example.test' } }
      else if (path === '/api/conversations') body = []
      else if (path === '/api/documents') body = [{ filename: '수입증빙.pdf', search_ready: true }]
      else if (path === '/api/consultation-cases' && req.method() === 'GET') body = list
      else if (path === '/api/consultation-cases' && req.method() === 'POST') {
        const input = JSON.parse(req.postData())
        current = { ...input, id: 'case-1', kind: 'income_tax', conversation_id: 'conversation-1', has_chat: false,
          created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
        list.push({ id: current.id, title: current.title, tax_year: current.tax_year, answered: 0, has_calculation: false })
        body = detail()
      } else if (path === '/api/consultation-cases/case-1' && req.method() === 'GET') body = detail()
      else if (path.endsWith('/facts')) { Object.assign(facts, JSON.parse(req.postData())); calculation = null; list[0].answered = Object.keys(facts).length; body = detail() }
      else if (path.includes('/documents/')) { const key = path.split('/').at(-1); docs[key] = JSON.parse(req.postData()); body = detail() }
      else if (path.endsWith('/calculate')) {
        calculation = { tax_year: current.tax_year, calculated_at: new Date().toISOString(),
          result: { tax_type: '소득세', steps: [{ label: '결정세액', amount: 1000 }], taxable_income: 10000,
            calculated_tax: 1000, final_tax: 1000, effective_rate: 0.01,
            source_articles: ['소득세법 제55조'], basis: { queried_on: '2024-12-31', effective_dates: ['2024-01-01'] } } }
        list[0].has_calculation = true; body = detail()
      }
      await route.fulfill({ status: path === '/api/consultation-cases' && req.method() === 'POST' ? 201 : 200, json: body })
    })
    await page.goto(process.env.UI_TEST_URL || 'http://localhost:3002')
    await page.getByLabel('이메일').fill('case@example.test')
    await page.locator('input[type=password]').fill('synthetic-password')
    await page.getByRole('button', { name: '로그인', exact: true }).last().click()
    await page.getByRole('button', { name: '상담 작업', exact: true }).click()
    await page.getByRole('button', { name: '새 상담' }).click()
    await page.getByRole('textbox', { name: '궁금한 내용' }).fill('종합소득세 계산과 근거를 확인하고 싶습니다.')
    await page.getByRole('button', { name: '상담 만들기' }).click()
    for (const answer of ['5000', '1000', '1', '0']) {
      await page.locator('#case-next-answer').fill(answer)
      await page.getByRole('button', { name: '저장하고 다음 질문' }).click()
    }
    await page.getByText('계산에 필요한 조건을 모두 확인했습니다.').waitFor()
    await page.getByLabel('수입금액 확인 자료 연결 문서').selectOption('수입증빙.pdf')
    await page.locator('.case-document').first().getByRole('button', { name: '연결' }).click()
    await page.getByText('내 문서 연결됨', { exact: false }).waitFor()
    await page.getByRole('button', { name: '종합소득세 계산하기' }).click()
    await page.getByText('1,000원', { exact: false }).first().waitFor()
    assert.deepEqual(errors, [])
    console.log('PASS: case creation, four clarification answers, document checklist and saved calculation')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the VAT tab sends card sales and prepaid tax, and drops general-only lines for a 간이과세자', () => {
  const general = FORMS.vat.toPayload({ ...FORMS.vat.defaults, sales: '15500', purchases: '4150', deemed_purchases: '3240',
    card_sales: '15840', prepaid_tax: '200' })
  assert.equal(general.sales, 155_000_000)
  assert.equal(general.deemed_purchases, 32_400_000)
  assert.equal(general.card_sales, 158_400_000)
  assert.equal(general.card_credit_eligible, true)
  const simple = FORMS.vat.toPayload({ ...FORMS.vat.defaults, is_simplified: true, business_type: '음식점업',
    sales: '6400', exempt_sales: '100', deemed_purchases: '500' })
  assert.equal(simple.exempt_sales, 0)
  assert.equal(simple.deemed_purchases, 0)
  assert.equal(simple.business_type, '음식점업')
})

test('the penalty tab sends the reduction months and late days, but not for late payment only', () => {
  const payload = FORMS.penalty.toPayload({ ...FORMS.penalty.defaults, unpaid_tax: '500', days_late: '60', filed_within_months: '2' })
  assert.deepEqual(payload, { unpaid_tax: 5_000_000, penalty_type: '무신고', is_negligent: false, days_late: 60,
    filed_within_months: 2, revenue: 0 })
  const late = FORMS.penalty.toPayload({ unpaid_tax: '500', penalty_type: '납부지연', days_late: '10', filed_within_months: '2', is_negligent: true })
  assert.equal(late.filed_within_months, 0)
  assert.equal(late.is_negligent, false)
})

test('a chat penalty calculation opens the tab and the follow-up repeats it', () => {
  const form = buildFormFromParams('penalty', { unpaid_tax: 5_000_000, penalty_type: '무신고', days_late: 60, filed_within_months: 2 })
  assert.equal(form.days_late, '60')
  const question = QUESTION_BUILDERS.penalty(form, { final_tax: 5_766_000 })
  assert.match(question, /납부지연 60일/)
  assert.match(question, /기한 후 2개월 안에 스스로 신고/)
})

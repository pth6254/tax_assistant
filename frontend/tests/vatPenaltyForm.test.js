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

test('every tax tab sends the penalty option, only with the facts its kind uses', () => {
  const none = FORMS.vat.toPayload({ ...FORMS.vat.defaults, sales: '1000', days_late: '60' })
  assert.deepEqual([none.penalty_type, none.days_late, none.reported_tax], ['없음', 0, 0])
  const late = FORMS.gift.toPayload({ ...FORMS.gift.defaults, gift_amount: '30000', penalty_type: '무신고',
    days_late: '60', filed_within_months: '2', reported_tax: '100' })
  assert.deepEqual([late.penalty_type, late.days_late, late.filed_within_months, late.reported_tax], ['무신고', 60, 2, 0])
  const unpaid = FORMS.capital.toPayload({ ...FORMS.capital.defaults, transfer_price: '1', acquisition_price: '1',
    penalty_type: '납부지연', reported_tax: '300', days_late: '10', filed_within_months: '2', is_negligent: true })
  assert.deepEqual([unpaid.reported_tax, unpaid.filed_within_months, unpaid.is_negligent], [3_000_000, 0, false])
})

test('a chat calculation with a penalty opens the tax tab and the follow-up repeats it', () => {
  const form = buildFormFromParams('gift', { gift_amount: 300_000_000, relation: '직계존비속', penalty_type: '무신고',
    days_late: 60, filed_within_months: 2 })
  assert.equal(form.penalty_type, '무신고')
  assert.equal(form.days_late, '60')
  const question = QUESTION_BUILDERS.gift(form, { final_tax: 44_264_000 })
  assert.match(question, /무신고 후 2개월 안에 신고/)
  assert.match(question, /납부지연 60일/)
})

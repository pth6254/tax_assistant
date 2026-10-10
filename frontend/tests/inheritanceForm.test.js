import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the inheritance tab sends the heirs and the deductions in won', () => {
  const form = { ...FORMS.inheritance.defaults, estate_value: '210000', financial_assets: '70000', debts: '31500',
    spouse_inheritance: '59000', children_count: '1', disabled_years: '63', prior_gifts: '10000' }
  const payload = FORMS.inheritance.toPayload(form)
  assert.equal(payload.estate_value, 2_100_000_000)
  assert.equal(payload.financial_assets, 700_000_000)
  assert.equal(payload.has_spouse, true)
  assert.equal(payload.spouse_inheritance, 590_000_000)
  assert.equal(payload.disabled_years, 63)
  assert.equal(payload.filed_on_time, true)
})

test('without a spouse no spouse inheritance is sent', () => {
  const payload = FORMS.inheritance.toPayload({ ...FORMS.inheritance.defaults, estate_value: '100000',
    has_spouse: false, spouse_inheritance: '50000' })
  assert.equal(payload.has_spouse, false)
  assert.equal(payload.spouse_inheritance, 0)
})

test('a chat inheritance calculation opens the tab and the follow-up repeats the heirs', () => {
  const form = buildFormFromParams('inheritance', { estate_value: 2_000_000_000, has_spouse: true, children_count: 2,
    spouse_inheritance: 0, prior_gifts: 300_000_000 })
  assert.equal(form.estate_value, '200000')
  assert.equal(form.children_count, '2')
  const question = QUESTION_BUILDERS.inheritance(form, { final_tax: 231_345_000 })
  assert.match(question, /배우자 실제 상속액 0만원/)
  assert.match(question, /사전증여 30000만원/)
  assert.match(question, /231,345,000원/)
})

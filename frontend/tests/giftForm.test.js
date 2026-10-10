import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the gift tab sends every fact the calculator needs', () => {
  const form = { ...FORMS.gift.defaults, gift_amount: '20000', prior_gifts_10y: '10000', prior_gift_tax: '700',
    prior_gift_taxable: '7000', generation_skipping: true }
  assert.deepEqual(FORMS.gift.toPayload(form), {
    gift_amount: 200_000_000, relation: '직계존비속', is_minor: false, prior_gifts_10y: 100_000_000, debts: 0,
    prior_gift_tax: 7_000_000, prior_gift_taxable: 70_000_000, deduction_used_10y: 0, marriage_birth: false,
    marriage_birth_used: 0, generation_skipping: true, filed_on_time: true,
  })
})

test('lineal-only facts are not sent for a spouse', () => {
  const payload = FORMS.gift.toPayload({ ...FORMS.gift.defaults, gift_amount: '80000', relation: '배우자',
    is_minor: true, generation_skipping: true, marriage_birth: true })
  assert.equal(payload.is_minor, false)
  assert.equal(payload.generation_skipping, false)
  assert.equal(payload.marriage_birth, false)
})

test('a chat gift calculation opens the tab with its values and the follow-up repeats them', () => {
  const form = buildFormFromParams('gift', { gift_amount: 500_000_000, relation: '직계존비속', debts: 200_000_000, filed_on_time: false })
  assert.equal(form.gift_amount, '50000')
  assert.equal(form.debts, '20000')
  assert.equal(form.filed_on_time, false)
  const question = QUESTION_BUILDERS.gift(form, { final_tax: 29_100_000 })
  assert.match(question, /인수 채무 20000만원/)
  assert.match(question, /29,100,000원/)
})

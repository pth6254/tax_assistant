import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the financial income tab sends won amounts and the withholding flag', () => {
  const form = { ...FORMS.financial.defaults, interest_income: '10000', dividend_gross_up: '2500.5' }
  assert.deepEqual(FORMS.financial.toPayload(form), {
    interest_income: 100_000_000, non_business_interest: 0, dividend_gross_up: 25_005_000, dividend_other: 0,
    other_income: 0, income_deductions: 1_500_000, withheld: true,
  })
  assert.equal(FORMS.financial.toPayload({ ...form, withheld: false }).withheld, false)
  assert.ok(TABS.some(tab => tab.key === 'financial'))
})

test('a chat calculation opens the financial tab with the same values', () => {
  assert.equal(TOOL_TO_TAB.financial_income_tax, 'financial')
  const form = buildFormFromParams('financial', { interest_income: 100_000_000, income_deductions: 1_500_000, withheld: false })
  assert.equal(form.interest_income, '10000')
  assert.equal(form.income_deductions, '150')
  assert.equal(form.withheld, false)
})

test('the follow-up question repeats the stated amounts', () => {
  const question = QUESTION_BUILDERS.financial({ interest_income: '10000', dividend_gross_up: '100', dividend_other: '50' },
    { final_tax: 15_880_000 })
  assert.match(question, /이자 10000만원/)
  assert.match(question, /배당 150만원/)
  assert.match(question, /15,880,000원/)
})

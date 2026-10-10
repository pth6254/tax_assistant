import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('one comprehensive income tab sends every income kind in won', () => {
  const form = { ...FORMS.income.defaults, wage_income: '5000', interest_income: '3000', dividend_gross_up: '2500.5' }
  assert.deepEqual(FORMS.income.toPayload(form), {
    income: 0, expense: 0, wage_income: 50_000_000, other_income: 0, interest_income: 30_000_000,
    non_business_interest: 0, dividend_gross_up: 25_005_000, dividend_other: 0, withheld: true,
    personal_deduction_count: 1, other_deductions: 0, itemized_special_credits: false, sincere_business: false,
    other_tax_credits: 0, prepaid_tax: 0,
  })
  assert.equal(FORMS.income.toPayload({ ...form, withheld: false }).withheld, false)
  assert.ok(!TABS.some(tab => tab.key === 'financial'))
})

test('an old financial calculation opens the income tab with its deductions carried over', () => {
  assert.equal(TOOL_TO_TAB.financial_income_tax, 'income')
  const form = buildFormFromParams('income', { interest_income: 100_000_000, income_deductions: 1_500_000, withheld: false })
  assert.equal(form.interest_income, '10000')
  assert.equal(form.personal_deduction_count, '0')
  assert.equal(form.other_deductions, '150')
  assert.equal(form.withheld, false)
})

test('the follow-up question repeats only the stated incomes', () => {
  const question = QUESTION_BUILDERS.income({ wage_income: '5000', interest_income: '10000', dividend_gross_up: '100', dividend_other: '50' },
    { final_tax: 15_880_000 })
  assert.match(question, /총급여 5000만원/)
  assert.match(question, /이자 10000만원/)
  assert.match(question, /배당 150만원/)
  assert.doesNotMatch(question, /사업 수입/)
  assert.match(question, /15,880,000원/)
})

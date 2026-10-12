import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

const NO_PENALTY = { penalty_type: '없음', reported_tax: 0, is_negligent: false, days_late: 0, filed_within_months: 0, penalty_revenue: 0, as_of: null }

test('one comprehensive income tab sends every income kind in won', () => {
  const form = { ...FORMS.income.defaults, wage_income: '5000', interest_income: '3000', dividend_gross_up: '2500.5' }
  assert.deepEqual(FORMS.income.toPayload(form), { ...NO_PENALTY,
    income: 0, expense: 0, wage_income: 50_000_000, other_income: 0, interest_income: 30_000_000,
    non_business_interest: 0, dividend_gross_up: 25_005_000, dividend_other: 0, withheld: true,
    personal_deduction_count: 1, other_deductions: 0, itemized_special_credits: false, sincere_business: false,
    other_tax_credits: 0, prepaid_tax: 0, business_method: '장부', simple_rate: 0, simple_excess_rate: null,
    standard_rate: 0, major_expenses: 0, double_entry: false, pension_income: 0, private_pension: 0, pension_age: 0,
    misc_income: 0, misc_expense_rule: '60%', misc_expenses: 0, rental_income: 0, rental_expenses: 0,
    registered_rental: false, daily_wage: 0, daily_work_days: 0, virtual_transfer_price: 0,
    virtual_acquisition_price: 0, virtual_expenses: 0, virtual_held_before_2027: false, virtual_value_2026_end: 0,
    rental_deposits: 0, rental_house_count: 0, religious_income: 0, religious_as_wage: false,
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

test('estimated business income sends the rates and drops the book expense', () => {
  const payload = FORMS.income.toPayload({ ...FORMS.income.defaults, income: '10000', expense: '500',
    business_method: '기준경비율', simple_rate: '93.7', standard_rate: '6', major_expenses: '6000' })
  assert.equal(payload.expense, 0)
  assert.equal(payload.simple_rate, 93.7)
  assert.equal(payload.major_expenses, 60_000_000)
  const form = buildFormFromParams('income', { simple_excess_rate: null, private_pension: 18_000_000, pension_age: 72 })
  assert.equal(form.simple_excess_rate, undefined)
  assert.equal(form.private_pension, '1800')
  assert.equal(form.pension_age, '72')
})

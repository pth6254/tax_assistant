import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

const NO_PENALTY = { penalty_type: '없음', reported_tax: 0, is_negligent: false, days_late: 0, filed_within_months: 0, penalty_revenue: 0, as_of: null }

test('the retirement tab sends the pay and the years of service', () => {
  assert.ok(TABS.some(tab => tab.key === 'retirement'))
  assert.equal(TOOL_TO_TAB.retirement, 'retirement')
  assert.deepEqual(FORMS.retirement.toPayload({ retirement_pay: '10000', service_years: '20' }),
    { ...NO_PENALTY, retirement_pay: 100_000_000, service_years: 20, prepaid_tax: 0, pension_transfer: 0 })
  const form = buildFormFromParams('retirement', { retirement_pay: 100_000_000, service_years: 20 })
  assert.match(QUESTION_BUILDERS.retirement(form, { final_tax: 1_120_000 }), /근속 20년.*1,120,000원/)
})

test('the finishing options are sent only where they apply', () => {
  const right = FORMS.capital.toPayload({ ...FORMS.capital.defaults, asset_type: '조합원입주권', transfer_price: '1', acquisition_price: '1',
    is_one_home: true, prior_same_year_taxable: '5000' })
  assert.deepEqual([right.is_one_home, right.prior_same_year_taxable], [true, 50_000_000])
  const stock = FORMS.capital.toPayload({ ...FORMS.capital.defaults, asset_type: '주식', transfer_price: '1', acquisition_price: '1',
    prior_same_year_taxable: '5000' })
  assert.equal(stock.prior_same_year_taxable, 0)
  const gift = FORMS.gift.toPayload({ ...FORMS.gift.defaults, gift_amount: '30000', reported_taxable: '15000' })
  assert.equal(gift.reported_taxable, 0)
  const under = FORMS.gift.toPayload({ ...FORMS.gift.defaults, gift_amount: '30000', penalty_type: '과소신고', reported_taxable: '15000' })
  assert.equal(under.reported_taxable, 150_000_000)
  const income = FORMS.income.toPayload({ ...FORMS.income.defaults, rental_house_count: '3' })
  assert.equal(income.rental_house_count, 0)
  assert.equal(FORMS.retirement.toPayload({ retirement_pay: '10000', service_years: '20', pension_transfer: '10000' }).pension_transfer, 100_000_000)
})

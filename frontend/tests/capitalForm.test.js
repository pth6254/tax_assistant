import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

const NO_PENALTY = { penalty_type: '없음', reported_tax: 0, is_negligent: false, days_late: 0, filed_within_months: 0, penalty_revenue: 0 }

test('the capital gains tab sends the exemption facts', () => {
  const form = { ...FORMS.capital.defaults, transfer_price: '150000', acquisition_price: '100000', holding_years: '7',
    is_one_home: true, residence_years: '5' }
  assert.deepEqual(FORMS.capital.toPayload(form), { ...NO_PENALTY,
    transfer_price: 1_500_000_000, acquisition_price: 1_000_000_000, expenses: 0, holding_years: 7,
    asset_type: '주택', is_one_home: true, residence_years: 5, acquired_in_adjusted_area: false,
    multi_home_surcharge: '없음', non_business_land: false, unregistered: false, pre_approval_gain: 0,
    pre_approval_years: 0, stock_market: '국내비상장', major_shareholder: false, sme: false, same_group_loss: 0,
  })
})

test('stock and land facts are sent only for their own asset types', () => {
  const stock = FORMS.capital.toPayload({ ...FORMS.capital.defaults, asset_type: '주식', transfer_price: '10000',
    acquisition_price: '5000', stock_market: '국외', major_shareholder: true, is_one_home: true, non_business_land: true })
  assert.equal(stock.stock_market, '국외')
  assert.equal(stock.major_shareholder, true)
  assert.equal(stock.is_one_home, false)
  assert.equal(stock.non_business_land, false)
  assert.equal(stock.unregistered, false)
  const land = FORMS.capital.toPayload({ ...FORMS.capital.defaults, asset_type: '토지·건물', non_business_land: true,
    major_shareholder: true })
  assert.equal(land.non_business_land, true)
  assert.equal(land.major_shareholder, false)
})

test('a chat calculation opens the capital tab with the same facts', () => {
  const form = buildFormFromParams('capital', { transfer_price: 300_000_000, asset_type: '토지·건물',
    multi_home_surcharge: '없음', residence_years: 0 })
  assert.equal(form.transfer_price, '30000')
  assert.equal(form.asset_type, '토지·건물')
  assert.equal(form.residence_years, '0')
})

test('the follow-up question repeats the one-home facts', () => {
  const question = QUESTION_BUILDERS.capital({ transfer_price: '150000', acquisition_price: '100000', holding_years: '7',
    is_one_home: true, residence_years: '5' }, { final_tax: 6_165_000 })
  assert.match(question, /1세대 1주택, 거주기간 5년/)
  assert.match(question, /6,165,000원/)
})

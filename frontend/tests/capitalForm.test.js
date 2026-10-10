import { test } from 'node:test'
import assert from 'node:assert/strict'
import { FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the capital gains tab sends the exemption facts', () => {
  const form = { ...FORMS.capital.defaults, transfer_price: '150000', acquisition_price: '100000', holding_years: '7',
    is_one_home: true, residence_years: '5' }
  assert.deepEqual(FORMS.capital.toPayload(form), {
    transfer_price: 1_500_000_000, acquisition_price: 1_000_000_000, expenses: 0, holding_years: 7,
    asset_type: '주택', is_one_home: true, residence_years: 5, acquired_in_adjusted_area: false,
    multi_home_surcharge: '없음',
  })
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

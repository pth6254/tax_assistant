import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TABS, TOOL_TO_TAB, FORMS, buildFormFromParams } from '../src/components/Calculator/forms.js'

test('the calculators are the six tax units, with no separate virtual asset or penalty tab', () => {
  assert.deepEqual(TABS.map(t => t.label), ['종합소득세', '퇴직소득세', '양도소득세', '상속세', '증여세', '부가가치세'])
  assert.equal(TOOL_TO_TAB.penalty_tax, undefined)
})

test('the income tax tab sends the virtual asset year-end price only for coins held before 2027', () => {
  const later = FORMS.income.toPayload({ ...FORMS.income.defaults, virtual_transfer_price: '5000',
    virtual_acquisition_price: '1000', virtual_value_2026_end: '3000' })
  assert.deepEqual([later.virtual_transfer_price, later.virtual_value_2026_end], [50_000_000, 0])
  const held = FORMS.income.toPayload({ ...FORMS.income.defaults, virtual_transfer_price: '5000',
    virtual_acquisition_price: '1000', virtual_held_before_2027: true, virtual_value_2026_end: '3000' })
  assert.equal(held.virtual_value_2026_end, 30_000_000)
})

test('an earlier virtual asset chat result opens in the income tax tab', () => {
  assert.equal(TOOL_TO_TAB.virtual_asset, 'income')
  const form = buildFormFromParams('income', { transfer_price: 50_000_000, acquisition_price: 10_000_000 })
  assert.deepEqual([form.virtual_transfer_price, form.virtual_acquisition_price], ['5000', '1000'])
})

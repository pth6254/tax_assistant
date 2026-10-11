import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, FORMS } from '../src/components/Calculator/forms.js'

test('the virtual asset tab sends the year-end price only for coins held before 2027', () => {
  assert.equal(TOOL_TO_TAB.virtual_asset, 'virtual')
  const later = FORMS.virtual.toPayload({ transfer_price: '5000', acquisition_price: '1000', value_2026_end: '3000' })
  assert.equal(later.value_2026_end, 0)
  const held = FORMS.virtual.toPayload({ transfer_price: '5000', acquisition_price: '1000', held_before_2027: true, value_2026_end: '3000' })
  assert.equal(held.value_2026_end, 30_000_000)
})

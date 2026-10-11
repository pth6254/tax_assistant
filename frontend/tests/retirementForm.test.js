import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TOOL_TO_TAB, TABS, FORMS, buildFormFromParams, QUESTION_BUILDERS } from '../src/components/Calculator/forms.js'

test('the retirement tab sends the pay and the years of service', () => {
  assert.ok(TABS.some(tab => tab.key === 'retirement'))
  assert.equal(TOOL_TO_TAB.retirement, 'retirement')
  assert.deepEqual(FORMS.retirement.toPayload({ retirement_pay: '10000', service_years: '20' }),
    { retirement_pay: 100_000_000, service_years: 20, prepaid_tax: 0 })
  const form = buildFormFromParams('retirement', { retirement_pay: 100_000_000, service_years: 20 })
  assert.match(QUESTION_BUILDERS.retirement(form, { final_tax: 1_120_000 }), /근속 20년.*1,120,000원/)
})

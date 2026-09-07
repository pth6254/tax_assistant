import test from 'node:test'
import assert from 'node:assert/strict'
import { errorMessage } from '../src/api/http.js'

test('UI normalizes structured and validation errors safely', () => {
  assert.equal(errorMessage({ detail: { message: '조건 확인 필요' } }), '조건 확인 필요')
  assert.equal(errorMessage(new Error('연결 오류')), '연결 오류')
  assert.equal(typeof errorMessage({ detail: [{ msg: 'invalid' }] }), 'string')
})

test('calculator prefills retain single-won precision and zero people', async () => {
  const { createServer } = await import('vite')
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try {
    const { FORMS, buildFormFromParams } = await server.ssrLoadModule('/src/components/Calculator/forms.js')
    const form = buildFormFromParams('income', { income: 123456789, personal_deduction_count: 0 })
    const payload = FORMS.income.toPayload(form)
    assert.equal(payload.income, 123456789)
    assert.equal(payload.personal_deduction_count, 0)
    assert.deepEqual(FORMS.capital.fields.find(f => f.key === 'asset_type').options, ['부동산'])
  } finally { await server.close() }
})

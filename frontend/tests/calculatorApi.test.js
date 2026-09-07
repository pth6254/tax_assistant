import test from 'node:test'
import assert from 'node:assert/strict'
import { calcIncomeTax } from '../src/api/calculatorApi.js'

test('calculator handles structured failures, validation and network errors', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: {
      code: 'missing_tax_data', message: '세율 데이터 확인 필요', retryable: false,
    } }), { status: 503 })
    await assert.rejects(calcIncomeTax({ income: 1 }), error =>
      error.message === '세율 데이터 확인 필요' && error.code === 'missing_tax_data' && !error.retryable)
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: [{ type: 'missing' }] }), { status: 422 })
    await assert.rejects(calcIncomeTax({}), error => error.code === 'missing_input' && !error.retryable)
    globalThis.fetch = async () => { throw new TypeError('network') }
    await assert.rejects(calcIncomeTax({ income: 1 }), error => error.code === 'network_error' && error.retryable)
    globalThis.fetch = async () => new Response(JSON.stringify({ final_tax: 0 }))
    assert.equal((await calcIncomeTax({ income: 0 })).final_tax, 0)
  } finally { globalThis.fetch = original }
})

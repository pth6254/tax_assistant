import test from 'node:test'
import assert from 'node:assert/strict'
import { sourceDates } from '../src/components/Chat/sourceDates.js'

test('the panel shows since when the wording has been in force when it is earlier than the version', () => {
  assert.equal(sourceDates({ effective_from: '20260701', in_force_since: '20220101' }),
    '자료 시행일: 2026-07-01 (이 문구는 2022-01-01부터 같음)')
  assert.equal(sourceDates({ effective_from: '20260701', in_force_since: '20260701' }), '자료 시행일: 2026-07-01')
  assert.equal(sourceDates({ effective_from: '2025-01-01' }), '자료 시행일: 2025-01-01')
  assert.equal(sourceDates({}), '자료 시행일 미확인')
})

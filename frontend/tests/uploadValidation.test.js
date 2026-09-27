import test from 'node:test'
import assert from 'node:assert/strict'
import { MAX_DOCUMENT_BYTES, validateDocumentFile } from '../src/components/Documents/uploadValidation.js'

test('all supported formats pass case-insensitive extension validation', () => {
  for (const name of ['a.pdf', 'b.DOCX', 'c.hwpx', 'd.pptx', 'e.html', 'f.htm']) {
    assert.equal(validateDocumentFile({ name, size: 100 }), '')
  }
})

test('unsupported, empty and oversized files fail before upload', () => {
  assert.match(validateDocumentFile({ name: 'legacy.hwp', size: 100 }), /지원하지/)
  assert.match(validateDocumentFile({ name: 'empty.pdf', size: 0 }), /빈 파일/)
  assert.match(validateDocumentFile({ name: 'huge.pdf', size: MAX_DOCUMENT_BYTES + 1 }), /50MB/)
  assert.equal(validateDocumentFile({ name: 'limit.pdf', size: MAX_DOCUMENT_BYTES }), '')
})

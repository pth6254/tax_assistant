import { requestJson } from './http'

const path = filename => `/api/documents/${encodeURIComponent(filename)}`
export const reviewDocument = filename => requestJson(`${path(filename)}/review`)
export const saveDocumentReview = (filename, fields, dates = [], expectedSha256, expectedReviewedAt) => requestJson(`${path(filename)}/review`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ fields, dates, expected_sha256: expectedSha256, expected_reviewed_at: expectedReviewedAt }),
})
export const originalPdfUrl = filename => `${path(filename)}/file`

import { requestJson } from './http'

const path = filename => `/api/documents/${encodeURIComponent(filename)}`
export const reviewDocument = filename => requestJson(`${path(filename)}/review`)
export const saveDocumentReview = (filename, fields, dates = []) => requestJson(`${path(filename)}/review`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fields, dates }),
})
export const originalPdfUrl = filename => `${path(filename)}/file`

import { requestJson } from './http'
export const listDocuments = () => requestJson('/api/documents')
export const deleteDocument = filename => requestJson(`/api/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' })

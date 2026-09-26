import { requestJson } from './http'

const BASE = '/api/consultation-cases'
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const listCases = () => requestJson(BASE)
export const createCase = body => requestJson(BASE, json('POST', body))
export const getCase = id => requestJson(`${BASE}/${encodeURIComponent(id)}`)
export const updateCaseFacts = (id, body) => requestJson(`${BASE}/${encodeURIComponent(id)}/facts`, json('PATCH', body))
export const updateCaseDocument = (id, slot, body) => requestJson(`${BASE}/${encodeURIComponent(id)}/documents/${encodeURIComponent(slot)}`, json('PUT', body))
export const clearCaseDocument = (id, slot) => requestJson(`${BASE}/${encodeURIComponent(id)}/documents/${encodeURIComponent(slot)}`, { method: 'DELETE' })
export const calculateCase = id => requestJson(`${BASE}/${encodeURIComponent(id)}/calculate`, { method: 'POST' })
export const ensureCaseConversation = id => requestJson(`${BASE}/${encodeURIComponent(id)}/conversation`, { method: 'POST' })
export const deleteCase = id => requestJson(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' })

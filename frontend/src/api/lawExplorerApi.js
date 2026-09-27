import { requestJson } from './http'
const base = '/api/law-explorer'
const query = params => new URLSearchParams(params).toString()
export const explorerLaws = () => requestJson(`${base}/laws`)
export const explorerArticle = params => requestJson(`${base}/article?${query(params)}`)
export const explorerCompare = params => requestJson(`${base}/compare?${query(params)}`)

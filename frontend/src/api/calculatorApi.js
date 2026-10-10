const BASE = '/api/calculator'

async function post(path, body) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  })
  } catch {
    throw Object.assign(new Error('서버에 연결하지 못했습니다. 연결을 확인하고 다시 계산해 주세요.'), { code: 'network_error', retryable: true })
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    const detail = err.detail
    if (detail && !Array.isArray(detail) && typeof detail === 'object') {
      throw Object.assign(new Error(detail.message || '계산에 실패했습니다.'), { code: detail.code, retryable: detail.retryable === true })
    }
    const missing = Array.isArray(detail) && detail.some(e => e.type === 'missing')
    const message = res.status === 401 ? '로그인 후 다시 계산해 주세요.'
      : res.status === 422 ? (missing ? '필수 입력을 확인해 주세요.' : '입력값의 형식과 범위를 확인해 주세요.')
      : '계산을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.'
    throw Object.assign(new Error(message), { code: missing ? 'missing_input' : 'request_failed', retryable: res.status >= 500 })
  }
  return res.json()
}

export const calcIncomeTax    = (data) => post('/income-tax', data)
export const calcCapitalGains = (data) => post('/capital-gains', data)
export const calcInheritance  = (data) => post('/inheritance', data)
export const calcGiftTax      = (data) => post('/gift', data)
export const calcVat          = (data) => post('/vat', data)
export const calcPenaltyTax   = (data) => post('/penalty-tax', data)

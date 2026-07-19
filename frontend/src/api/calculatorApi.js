const BASE = '/api/calculator'

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '계산 오류가 발생했습니다.')
  }
  return res.json()
}

export const calcIncomeTax    = (data) => post('/income-tax', data)
export const calcCapitalGains = (data) => post('/capital-gains', data)
export const calcInheritance  = (data) => post('/inheritance', data)
export const calcGiftTax      = (data) => post('/gift', data)
export const calcVat          = (data) => post('/vat', data)
export const calcPenaltyTax   = (data) => post('/penalty-tax', data)

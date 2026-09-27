export const getTaxSchedule = async () => {
  const res = await fetch('/api/tax-schedule', { credentials: 'include' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '세무 일정을 불러오지 못했습니다.')
  return data
}

export const getOfficialTaxCalendar = async (year, month, refresh = false) => {
  const params = new URLSearchParams({ year: String(year), month: String(month) })
  if (refresh) params.set('refresh', 'true')
  const res = await fetch(`/api/tax-schedule/official?${params}`, { credentials: 'include' })
  const data = await res.json()
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '국세청 일정을 불러오지 못했습니다.')
  return data
}

const personalRequest = async (url, options = {}) => {
  const response = await fetch(url, { credentials: 'include', ...options })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '내 일정을 변경하지 못했습니다.')
  return data
}
export const getPersonalEvents = (year, month) => personalRequest(`/api/tax-schedule/personal?year=${year}&month=${month}`)
export const getUpcomingPersonalEvents = () => personalRequest('/api/tax-schedule/personal/upcoming')
export const watchOfficialEvent = event => personalRequest('/api/tax-schedule/personal', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ due_date: event.date, title: event.title }),
})
export const updatePersonalEvent = (id, status) => personalRequest(`/api/tax-schedule/personal/${encodeURIComponent(id)}`, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
})
export const removePersonalEvent = id => personalRequest(`/api/tax-schedule/personal/${encodeURIComponent(id)}`, { method: 'DELETE' })

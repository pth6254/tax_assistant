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

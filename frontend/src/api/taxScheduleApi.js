export const getTaxSchedule = async () => {
  const res = await fetch('/api/tax-schedule', { credentials: 'include' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '세무 일정을 불러오지 못했습니다.')
  return data
}

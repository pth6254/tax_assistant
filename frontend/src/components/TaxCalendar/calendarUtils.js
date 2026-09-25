export function shiftMonth(year, month, offset) {
  const next = new Date(year, month - 1 + offset, 1)
  return { year: next.getFullYear(), month: next.getMonth() + 1 }
}

export function parseMonthSelection(value, currentYear) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return null
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5, 7))
  if (year < 2000 || year > currentYear + 1) return null
  return { year, month }
}

export function monthCells(year, month) {
  const firstDay = new Date(year, month - 1, 1).getDay()
  const lastDay = new Date(year, month, 0).getDate()
  return [...Array(firstDay).fill(null), ...Array.from({ length: lastDay }, (_, i) => i + 1)]
}

export function eventsOnDay(events, year, month, day) {
  const key = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  return events.filter(event => event.date === key)
}

import test from 'node:test'
import assert from 'node:assert/strict'
import { eventsOnDay, monthCells, parseMonthSelection, shiftMonth } from '../src/components/TaxCalendar/calendarUtils.js'

test('month navigation crosses years and calendar aligns Sunday-first', () => {
  assert.deepEqual(shiftMonth(2026, 12, 1), { year: 2027, month: 1 })
  assert.deepEqual(shiftMonth(2026, 1, -1), { year: 2025, month: 12 })
  const cells = monthCells(2026, 10)
  assert.equal(cells.length, 35)
  assert.equal(cells[4], 1)
  assert.equal(cells.at(-1), 31)
})

test('day events use posted dates without calculating a new deadline', () => {
  const events = [{ date: '2026-10-26', title: '부가가치세 예정신고' }]
  assert.deepEqual(eventsOnDay(events, 2026, 10, 26), events)
  assert.deepEqual(eventsOnDay(events, 2026, 10, 25), [])
})

test('direct month picker accepts supported periods and rejects invalid or distant dates', () => {
  assert.deepEqual(parseMonthSelection('2024-02', 2026), { year: 2024, month: 2 })
  assert.deepEqual(parseMonthSelection('2027-12', 2026), { year: 2027, month: 12 })
  assert.equal(parseMonthSelection('2028-01', 2026), null)
  assert.equal(parseMonthSelection('2026-13', 2026), null)
  assert.equal(parseMonthSelection('1999-12', 2026), null)
})

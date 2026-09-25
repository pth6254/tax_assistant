import { useEffect, useRef, useState } from 'react'
import { getOfficialTaxCalendar } from '../../api/taxScheduleApi'
import Icon from '../ui/Icon'
import { eventsOnDay, monthCells, parseMonthSelection, shiftMonth } from './calendarUtils'
import './taxCalendar.css'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']
const today = new Date()

export default function TaxCalendarScreen() {
  const [period, setPeriod] = useState({ year: today.getFullYear(), month: today.getMonth() + 1 })
  const [day, setDay] = useState(today.getDate())
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [forceRefresh, setForceRefresh] = useState(false)
  const monthPicker = useRef(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setData(null)
    setError('')
    getOfficialTaxCalendar(period.year, period.month, forceRefresh)
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) { setLoading(false); setForceRefresh(false) } })
    return () => { active = false }
  }, [period.year, period.month, reload])

  const goToMonth = next => {
    if (!next || next.year < 2000 || next.year > today.getFullYear() + 1) return
    setPeriod(next)
    setDay(next.year === today.getFullYear() && next.month === today.getMonth() + 1 ? today.getDate() : 1)
  }
  const move = offset => goToMonth(shiftMonth(period.year, period.month, offset))
  const openMonthPicker = () => {
    const input = monthPicker.current
    if (!input) return
    try { input.showPicker?.() } catch { input.focus() }
    if (!input.showPicker) input.focus()
  }
  const refresh = () => { setForceRefresh(true); setReload(value => value + 1) }
  const events = data?.events || []
  const selected = eventsOnDay(events, period.year, period.month, day)
  const checkedAt = data?.checked_at ? new Date(data.checked_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : null

  return <main className="workspace-page tax-calendar-page">
    <header className="page-header">
      <div><p className="eyebrow">OFFICIAL TAX CALENDAR</p><h1>세무일정</h1><p className="muted small">국세청에 게시된 신고·납부 일정을 날짜별로 확인하세요.</p></div>
      <a className="button secondary" href="https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do?mi=135747" target="_blank" rel="noopener noreferrer">국세청 원문 ↗</a>
    </header>
    <div className="page-scroll tax-calendar-scroll">
      <div className="calendar-intro">
        <div><span className="calendar-kicker">국세청 공식 게시 일정</span><h2>{period.year}년 {period.month}월</h2></div>
        <div className="calendar-controls">
          <button className="icon-button" aria-label="이전 달" onClick={() => move(-1)} disabled={period.year === 2000 && period.month === 1}><Icon name="chevron" style={{ transform: 'rotate(180deg)' }} /></button>
          <button className="button secondary calendar-today" onClick={() => goToMonth({ year: today.getFullYear(), month: today.getMonth() + 1 })}>이번 달</button>
          <button className="icon-button" aria-label="다음 달" onClick={() => move(1)} disabled={period.year === today.getFullYear() + 1 && period.month === 12}><Icon name="chevron" /></button>
          <div className="calendar-month-picker">
            <button className="icon-button" type="button" aria-label="연월 선택 달력 열기" onClick={openMonthPicker}><Icon name="calendar" size={18} /></button>
            <input ref={monthPicker} type="month" aria-label="조회할 연월" min="2000-01" max={`${today.getFullYear() + 1}-12`}
              value={`${period.year}-${String(period.month).padStart(2, '0')}`}
              onChange={event => goToMonth(parseMonthSelection(event.target.value, today.getFullYear()))} />
          </div>
          <button className="button secondary" onClick={refresh} disabled={loading}><Icon name="refresh" size={16} /> 다시 확인</button>
        </div>
      </div>
      {error && <div className="notice" role="alert">{error} <a href={`https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do?mi=135747&taxYear=${period.year}&taxMonth=${String(period.month).padStart(2, '0')}`} target="_blank" rel="noopener noreferrer">공식 페이지 확인 ↗</a></div>}
      {loading && <p className="calendar-loading" role="status"><span className="spinner" /> 국세청 일정을 확인하는 중…</p>}
      {data && <>
        <div className={`calendar-source ${data.stale ? 'is-stale' : ''}`}>
          <div><strong>{data.stale ? '최신 정보 확인 실패 · 이전 조회 결과' : '국세청 공식 일정'}</strong><span>마지막 확인 {checkedAt} · {events.length}건 게시</span></div>
          <a href={data.source_url} target="_blank" rel="noopener noreferrer">이 달의 원문 보기 ↗</a>
        </div>
        {!data.published && <p className="calendar-unpublished">이 달에 국세청이 게시한 일정이 없습니다. 아직 게시 전일 수도 있으니 공식 페이지를 확인하세요.</p>}
        <div className="calendar-layout">
          <section className="calendar-grid-card" aria-label={`${period.year}년 ${period.month}월 일정 달력`}>
            <div className="calendar-weekdays">{WEEKDAYS.map(name => <span key={name}>{name}</span>)}</div>
            <div className="calendar-grid">{monthCells(period.year, period.month).map((number, index) => {
              if (number === null) return <div className="calendar-blank" key={`blank-${index}`} />
              const daily = eventsOnDay(events, period.year, period.month, number)
              const isToday = period.year === today.getFullYear() && period.month === today.getMonth() + 1 && number === today.getDate()
              return <button key={number} className={`calendar-day ${number === day ? 'is-selected' : ''} ${isToday ? 'is-today' : ''}`} aria-pressed={number === day} aria-label={`${period.month}월 ${number}일, 일정 ${daily.length}건`} onClick={() => setDay(number)}>
                <span className="calendar-day-number">{number}</span>
                {daily.length > 0 && <><span className="calendar-day-event">{daily[0].title}</span>{daily.length > 1 && <span className="calendar-day-count">외 {daily.length - 1}건</span>}</>}
              </button>
            })}</div>
          </section>
          <aside className="calendar-agenda" aria-live="polite">
            <p className="calendar-agenda-eyebrow">선택한 날짜</p>
            <h3>{period.month}월 {day}일 <span>{selected.length}건</span></h3>
            {selected.length ? <ul>{selected.map((event, index) => <li key={`${event.title}-${index}`}><strong>{event.title}</strong>{event.note && <p>{event.note}</p>}</li>)}</ul> : <p className="calendar-no-events">이 날짜에 게시된 일정이 없습니다.</p>}
          </aside>
        </div>
        <p className="calendar-disclaimer">국세청 전체 게시 일정입니다. 사업자 유형·과세기간·예외 요건에 따라 실제 신고 의무는 달라질 수 있습니다. 이 화면은 개인별 의무 판정이나 신고 완료 확인을 제공하지 않습니다. 최신 기한은 원문을 다시 확인하세요.</p>
      </>}
    </div>
  </main>
}

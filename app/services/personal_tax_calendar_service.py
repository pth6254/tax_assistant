"""User-selected official calendar events and local preparation state."""
from datetime import date, timedelta
import uuid

from fastapi import HTTPException

from app.database import get_pool
from app.services.official_tax_calendar import get_official_month, CalendarUnavailable


def identity(user_id):
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(401, '로그인이 필요합니다.') from None


def output(row):
    data = dict(row)
    data['id'] = str(data['id'])
    data['due_date'] = data['due_date'].isoformat()
    for key in ('created_at', 'updated_at'):
        if key in data:
            data[key] = data[key].isoformat()
    return data


async def list_events(user_id, year=None, month=None, upcoming=False):
    uid = identity(user_id)
    pool = await get_pool()
    if upcoming:
        rows = await pool.fetch('''SELECT * FROM personal_tax_events WHERE user_id=$1
            AND due_date BETWEEN $2 AND $3 AND status NOT IN ('done','not_applicable')
            ORDER BY due_date,title''', uid, date.today()-timedelta(days=7), date.today()+timedelta(days=30))
    else:
        rows = await pool.fetch('''SELECT * FROM personal_tax_events WHERE user_id=$1
            AND EXTRACT(YEAR FROM due_date)=$2 AND EXTRACT(MONTH FROM due_date)=$3
            ORDER BY due_date,title''', uid, year, month)
    return [output(row) for row in rows]


async def watch_event(user_id, due_date, title):
    uid = identity(user_id)
    if due_date.year > date.today().year + 1:
        raise HTTPException(422, '다음 연도까지만 선택할 수 있습니다.')
    try:
        month = await get_official_month(due_date.year, due_date.month, refresh=True)
    except CalendarUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    match = next((event for event in month['events']
                  if event['date'] == due_date.isoformat() and event['title'] == title), None)
    if match is None:
        raise HTTPException(422, '현재 공식 일정에서 해당 날짜와 제목을 확인하지 못했습니다.')
    pool = await get_pool()
    row = await pool.fetchrow('''INSERT INTO personal_tax_events
        (user_id,due_date,title,note,source_url) VALUES($1,$2,$3,$4,$5)
        ON CONFLICT(user_id,due_date,title) DO UPDATE SET note=EXCLUDED.note,
            source_url=EXCLUDED.source_url,updated_at=now()
        RETURNING *''', uid, due_date, title, match['note'], month['source_url'])
    return output(row)


async def set_status(user_id, event_id, status):
    try:
        eid = uuid.UUID(str(event_id))
    except (ValueError, TypeError):
        raise HTTPException(404, '저장한 일정을 찾을 수 없습니다.') from None
    pool = await get_pool()
    row = await pool.fetchrow('''UPDATE personal_tax_events SET status=$1,updated_at=now()
        WHERE id=$2 AND user_id=$3 RETURNING *''', status, eid, identity(user_id))
    if not row:
        raise HTTPException(404, '저장한 일정을 찾을 수 없습니다.')
    return output(row)


async def remove_event(user_id, event_id):
    try:
        eid = uuid.UUID(str(event_id))
    except (ValueError, TypeError):
        raise HTTPException(404, '저장한 일정을 찾을 수 없습니다.') from None
    pool = await get_pool()
    removed = await pool.fetchval('''DELETE FROM personal_tax_events
        WHERE id=$1 AND user_id=$2 RETURNING id''', eid, identity(user_id))
    if not removed:
        raise HTTPException(404, '저장한 일정을 찾을 수 없습니다.')
    return {'status': 'deleted'}

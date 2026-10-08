"""Decide by dates alone whether a dated question may rely on a cited version.

A record is in force from its effective date until the day before the next version
(`effective_to`), or until today for the current index. If an event falls entirely
inside that window, that version governed the event, so the record can support a
definite legal claim about it. Archived versions enter through
historical_evidence. Anything else (a partly covered period, a future date, an
unparseable date or a record without an effective date) stays unresolved and
keeps the historical gate. Supplementary provisions (부칙) can still apply different rules; the
rendered note says so instead of claiming they were checked.
"""
import calendar
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

from app.services.evidence import is_official

_DATE = re.compile(
    r"(?P<year>\d{4})\s*년(?:\s*(?P<month>\d{1,2})\s*월(?:\s*(?P<day>\d{1,2})\s*일)?)?"
    r"|(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})")


def event_interval(value):
    """'2026년' → whole year, '2026년 6월' → month, '2026년 6월 1일'/'2026-06-01' → day."""
    match = _DATE.fullmatch((value or "").strip())
    if not match:
        return None
    year = int(match["year"] or match["y"])
    month = match["month"] or match["m"]
    day = match["day"] or match["d"]
    try:
        if month is None:
            return date(year, 1, 1), date(year, 12, 31)
        month = int(month)
        if day is None:
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        point = date(year, month, int(day))
        return point, point
    except ValueError:
        return None


def is_event_date(value):
    """Durations such as '3년 6개월' describe facts, not when the event happened."""
    return event_interval(value) is not None


def effective_date(record):
    try:
        return date.fromisoformat((record.effective_from or "").replace("-", ""))
    except ValueError:
        return None


def in_force_until(record, today):
    try:
        return date.fromisoformat(record.effective_to.replace("-", "")) if record.effective_to else today
    except ValueError:
        return None


def covers(record, interval, today):
    start, end = effective_date(record), in_force_until(record, today)
    return start is not None and end is not None and start <= interval[0] and interval[1] <= min(end, today)


def unresolved_dates(dates, records, today=None):
    """Dates for which the given versions are not shown to have governed."""
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    official = [record for record in records if is_official(record)]
    if not official:
        return list(dates)
    unresolved = []
    for value in dates:
        interval = event_interval(value)
        if interval is None or not all(covers(record, interval, today) for record in official):
            unresolved.append(value)
    return unresolved


def covered_by_current_version(dates, records, today=None):
    return bool(dates) and not unresolved_dates(dates, records, today)

"""Decide by dates alone whether a dated question may rely on the stored current version.

Official records in the current index are the version in force today. If an event
falls entirely between a record's effective date and today, that version governed
the event, so the record can support a definite legal claim about it. Anything
else (an earlier or partly earlier period, a future date, an unparseable date or
a record without an effective date) stays unresolved and keeps the historical
gate. Supplementary provisions (부칙) can still apply different rules; the
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


def unresolved_dates(dates, records, today=None):
    """Dates for which the given current versions are not shown to have governed."""
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    official = [record for record in records if is_official(record)]
    effective = [effective_date(record) for record in official]
    if not official or any(value is None for value in effective):
        return list(dates)
    latest = max(effective)
    unresolved = []
    for value in dates:
        interval = event_interval(value)
        if interval is None or interval[0] < latest or interval[1] > today:
            unresolved.append(value)
    return unresolved


def covered_by_current_version(dates, records, today=None):
    return bool(dates) and not unresolved_dates(dates, records, today)

"""Read the NTS public monthly tax calendar without deriving deadlines ourselves."""

import asyncio
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import re

import httpx

_URL = "https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do"
_TTL = timedelta(minutes=30)
_STALE_LIMIT = timedelta(hours=24)
_cache: dict[tuple[int, int], dict] = {}
_lock = asyncio.Lock()


class CalendarUnavailable(Exception):
    pass


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def source_url(year: int, month: int) -> str:
    return f"{_URL}?mi=135747&taxYear={year}&taxMonth={month:02d}"


def parse_month(html: str, year: int, month: int) -> list[dict]:
    """Fail closed when NTS changes the selected period or table structure."""
    section = html.partition('id="taxSchdulList"')[2]
    selected_year = re.search(r'class="on"\s*>\s*<a[^>]+taxYear=(\d{4})&amp;taxMonth=', section)
    # NTS currently emits literal '&' inside its own links, not '&amp;'.
    if selected_year is None:
        selected_year = re.search(r'class="on"\s*>\s*<a[^>]+taxYear=(\d{4})&taxMonth=', section)
    month_tabs = section.partition('class="tab_st2 ')[2]
    selected_month = re.search(r'class="on"\s*>\s*<a[^>]+taxMonth=(\d{2})&(?:amp;)?mi=', month_tabs)
    if not section or not selected_year or not selected_month or int(selected_year[1]) != year or int(selected_month[1]) != month:
        raise CalendarUnavailable("국세청 일정의 조회 연월을 확인할 수 없습니다.")
    table_start = section.find("<table", section.find("월별 일정 시작!"))
    table_end = section.find("</table>", table_start)
    if table_start < 0 or table_end < 0:
        raise CalendarUnavailable("국세청 월별 일정 표를 찾을 수 없습니다.")
    table = section[table_start:table_end + len("</table>")]
    if "월별 일정" not in table or "일정" not in table or "비고" not in table:
        raise CalendarUnavailable("국세청 일정 표 형식이 변경되었습니다.")
    parser = _TableRows()
    parser.feed(table)
    body = table.partition("<tbody>")[2].partition("</tbody>")[0]
    if not body and "<tbody>" not in table:
        raise CalendarUnavailable("국세청 일정 본문 형식이 변경되었습니다.")
    if body.count("<tr") != len(parser.rows):
        raise CalendarUnavailable("국세청 일정 행 형식이 변경되었습니다.")
    events = []
    for cells in parser.rows:
        if len(cells) != 5 or not cells[0].isdigit() or not cells[1].isdigit():
            raise CalendarUnavailable("국세청 일정 행을 해석할 수 없습니다.")
        try:
            due_date = datetime(year, int(cells[0]), int(cells[1])).date()
        except ValueError as exc:
            raise CalendarUnavailable("국세청 일정 날짜가 올바르지 않습니다.") from exc
        if due_date.month != month or not cells[2]:
            raise CalendarUnavailable("국세청 일정 행의 월 또는 제목이 올바르지 않습니다.")
        events.append({"date": due_date.isoformat(), "title": cells[2], "note": cells[3]})
    return events


async def get_official_month(year: int, month: int, *, refresh: bool = False) -> dict:
    key = (year, month)
    now = datetime.now(timezone.utc)
    cached = _cache.get(key)
    if cached and not refresh and now - cached["fetched_at"] < _TTL:
        return {**cached["payload"], "stale": False}
    async with _lock:
        now = datetime.now(timezone.utc)
        cached = _cache.get(key)
        if cached and not refresh and now - cached["fetched_at"] < _TTL:
            return {**cached["payload"], "stale": False}
        url = source_url(year, month)
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                response = await client.get(url, headers={"User-Agent": "TaxAssistant/1.0 (official calendar viewer)"})
                response.raise_for_status()
            events = parse_month(response.text, year, month)
        except (httpx.HTTPError, CalendarUnavailable) as exc:
            if cached and now - cached["fetched_at"] < _STALE_LIMIT:
                return {**cached["payload"], "stale": True}
            raise CalendarUnavailable("국세청 일정을 확인할 수 없습니다. 공식 페이지에서 직접 확인해 주세요.") from exc
        payload = {
            "year": year,
            "month": month,
            "events": events,
            "source_url": url,
            "checked_at": now.isoformat(),
            "published": bool(events),
        }
        _cache[key] = {"payload": payload, "fetched_at": now}
        return {**payload, "stale": False}

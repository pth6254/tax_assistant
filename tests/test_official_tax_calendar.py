"""NTS calendar extraction and API contract; never calls the public site in tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.official_tax_calendar import CalendarUnavailable, parse_month, source_url


def _html(rows: str, *, year: int = 2026, month: int = 10) -> str:
    return f'''<div id="taxSchdulList">
      <ul><li class="on"><a href="selectList.do?taxYear={year}&taxMonth={month:02d}&mi=135747">{year}년</a></li></ul>
      <div class="tab_st2_box"><ul class="tab_st2 Tab_w10"><li class="on"><a href="selectList.do?taxYear={year}&taxMonth={month:02d}&mi=135747">{month}월</a></li></ul></div>
      <!-- 월별 일정 시작! -->
      <table><caption>월별 일정 - 월, 일, 일정, 비고, 보내기 제공</caption>
      <thead><tr><th>월</th><th>일</th><th>일정</th><th>비고</th><th>보내기</th></tr></thead>
      <tbody>{rows}</tbody></table></div>'''


def test_parse_official_month_preserves_posted_due_date_and_note():
    html = _html('<tr><td>10</td><td>26</td><td>2026.2기 부가가치세 예정신고 납부</td><td>2026.7~9월분</td><td><a href="https://calendar.google.com">보내기</a></td></tr>')
    assert parse_month(html, 2026, 10) == [{
        "date": "2026-10-26", "title": "2026.2기 부가가치세 예정신고 납부", "note": "2026.7~9월분",
    }]


def test_parse_rejects_wrong_period_or_invalid_row():
    with pytest.raises(CalendarUnavailable):
        parse_month(_html("", month=9), 2026, 10)
    with pytest.raises(CalendarUnavailable):
        parse_month(_html("<tr><td>10</td><td>32</td><td>신고</td><td></td><td></td></tr>"), 2026, 10)
    with pytest.raises(CalendarUnavailable):
        parse_month("<html>temporary block</html>", 2026, 10)


def test_parse_empty_published_month():
    assert parse_month(_html(""), 2026, 10) == []


def test_parse_does_not_treat_changed_row_markup_as_empty_month():
    with pytest.raises(CalendarUnavailable):
        parse_month(_html("<tr><th>새 형식</th></tr>"), 2026, 10)


def test_source_url_is_fixed_official_host():
    assert source_url(2026, 10) == "https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do?mi=135747&taxYear=2026&taxMonth=10"


def test_official_calendar_auth_and_bounds(client, auth_cookie):
    assert client.get("/api/tax-schedule/official?year=2026&month=10").status_code == 401
    assert client.get("/api/tax-schedule/official?year=2026&month=13", cookies=auth_cookie).status_code == 422


def test_official_calendar_api_returns_source_and_stale_flag(client, auth_cookie):
    result = {"year": 2026, "month": 10, "events": [{"date": "2026-10-26", "title": "부가가치세 예정신고", "note": ""}],
              "source_url": source_url(2026, 10), "checked_at": "2026-09-25T00:00:00+00:00", "published": True, "stale": False}
    with patch("app.routers.tax_schedule.get_official_month", AsyncMock(return_value=result)):
        response = client.get("/api/tax-schedule/official?year=2026&month=10", cookies=auth_cookie)
    assert response.status_code == 200
    assert response.json() == result


def test_official_calendar_api_fails_closed(client, auth_cookie):
    with patch("app.routers.tax_schedule.get_official_month", AsyncMock(side_effect=CalendarUnavailable("국세청 확인 실패"))):
        response = client.get("/api/tax-schedule/official?year=2026&month=10", cookies=auth_cookie)
    assert response.status_code == 503

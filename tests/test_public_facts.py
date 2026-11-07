"""Public facts found on official pages count only when the page's own words say them (no web or model call)."""
from datetime import date

import pytest

from app.services.calculator import public_facts as pf
from app.services.calculator.public_facts import Designation

PAGE = {"url": "https://www.molit.go.kr/a", "content":
        "국토교통부는 부산 해운대구, 수영구, 동래구를 2019.11.8. 조정대상지역에서 해제한다고 밝혔다. "
        "해운대구는 2016.11.3. 조정대상지역으로 지정된 바 있다."}


def item(quote, on="", off="", url=PAGE["url"]):
    return Designation(url=url, quote=quote, designated_on=on, released_on=off)


def test_place_words_skip_the_province():
    assert pf.place_words("부산 해운대") == ["해운대"]
    assert pf.place_words("서울시 서초구 반포동") == ["서초", "반포"]


def test_a_designation_counts_only_when_its_quote_is_on_the_page_with_the_place_and_dates():
    released = item("국토교통부는 부산 해운대구, 수영구, 동래구를 2019.11.8. 조정대상지역에서 해제한다고 밝혔다.", off="2019-11-08")
    designated = item("해운대구는 2016.11.3. 조정대상지역으로 지정된 바 있다.", on="2016-11-03")
    invented = item("해운대구는 2016.11.3. 조정대상지역으로 지정된 바 있다.", on="2017-08-03")   # a date not written
    elsewhere = item("해운대구는 2016.11.3. 조정대상지역으로 지정된 바 있다.", on="2016-11-03", url="https://x.kr")
    kept = pf.verified([released, designated, invented, elsewhere], [PAGE], "부산 해운대")
    assert kept == [released, designated]


@pytest.mark.parametrize("span, expected", [
    ((date(2018, 1, 1), date(2018, 12, 31)), True),     # inside 2016-11-03 ~ 2019-11-08
    ((date(2020, 3, 1), date(2020, 3, 31)), False),     # after the release
    ((date(2019, 11, 1), date(2019, 11, 30)), None),    # the month of the release
])
def test_the_status_for_a_span_comes_from_the_verified_dates(span, expected):
    items = [item("…", on="2016-11-03", off="2019-11-08")]
    assert pf.status_from(items, span) is expected


def test_a_listed_company_is_read_from_the_page_text_only():
    pages = [{"url": "https://kind.krx.co.kr/x", "content": "삼성전자(005930)는 유가증권시장 상장법인이다."}]
    market, note = pf.listed_in("삼성전자", pages)
    assert market == "국내상장" and "kind.krx.co.kr" in note and "다르면 알려주세요" in note
    assert pf.listed_in("카카오", pages) == (None, None)

"""Whether a house address lay in a 조정대상지역 on a date, from the designation record (주택법 제63조의2).

The capital gains calculator asks this (취득 당시 for the 1세대 1주택 residence rule, 양도일 현재 for the
multi-home surcharge) and users answer with an address ("서울시 서초구 반포동"). Only periods confirmed from
designation notices and their reporting are recorded; any other date or place returns None and the chat asks.

Confirmed record (checked 2026-11-07):
- 2017-08-03 ~ 2023-01-04: all 25 Seoul districts designated. The tax rule that reads this (소득세법 시행령
  제154조 ① residence requirement) applies only to houses acquired from 2017-08-03, so earlier dates are not needed.
- 2023-01-05: every designation released except Seoul 강남·서초·송파·용산 (1·3 대책; 뉴시스·이코노미스트 2023-01-03).
- 2025-10-16: all 25 Seoul districts and 12 Gyeonggi areas designated (10·15 대책; 정책브리핑 2025-10-15):
  과천, 광명, 성남 분당·수정·중원, 수원 영통·장안·팔달, 안양 동안, 용인 수지, 의왕, 하남.
- 2026-07-01: 화성시 동탄구, 용인시 기흥구, 구리시 designated (국토교통부 2026-06-30; 헤럴드경제·한국세정신문).
No release after these was found up to the check date. A date after CHECKED_ON takes the status in force on
it, and the note says that later notices are not reflected.
"""
import re
from dataclasses import dataclass
from datetime import date

CHECKED_ON = date(2026, 11, 7)
RESIDENCE_RULE_FROM = date(2017, 8, 3)   # 소득세법 시행령 부칙(2017.9.19): 2017.8.3 이후 취득분부터
OPEN = date(9999, 12, 31)

SEOUL_FOUR = [(date(2017, 8, 3), OPEN, True)]
SEOUL_OTHERS = [(date(2017, 8, 3), date(2023, 1, 5), True), (date(2023, 1, 5), date(2025, 10, 16), False),
                (date(2025, 10, 16), OPEN, True)]
GYEONGGI_2025 = [(date(2023, 1, 5), date(2025, 10, 16), False), (date(2025, 10, 16), OPEN, True)]
GYEONGGI_2026 = [(date(2023, 1, 5), date(2026, 7, 1), False), (date(2026, 7, 1), OPEN, True)]
ELSEWHERE = [(date(2023, 1, 5), OPEN, False)]

SEOUL_GU = ("종로", "중", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉", "노원", "은평", "서대문",
            "마포", "양천", "강서", "구로", "금천", "영등포", "동작", "관악", "서초", "강남", "송파", "강동")
SEOUL_FOUR_GU = {"강남", "서초", "송파", "용산"}
# Names that other cities also use; they count as Seoul only next to "서울".
SHARED_GU = {"중", "강서"}

# (pattern, label, record); checked before the city-level names below.
SPECIFIC = [
    (r"과천", "경기 과천시", GYEONGGI_2025), (r"광명", "경기 광명시", GYEONGGI_2025),
    (r"분당", "성남시 분당구", GYEONGGI_2025), (r"수정구", "성남시 수정구", GYEONGGI_2025),
    (r"중원구", "성남시 중원구", GYEONGGI_2025), (r"성남", "경기 성남시", GYEONGGI_2025),
    (r"영통", "수원시 영통구", GYEONGGI_2025), (r"장안구", "수원시 장안구", GYEONGGI_2025),
    (r"팔달", "수원시 팔달구", GYEONGGI_2025), (r"동안구|안양\s*(?:시\s*)?동안", "안양시 동안구", GYEONGGI_2025),
    (r"수지구|용인\s*(?:시\s*)?수지", "용인시 수지구", GYEONGGI_2025), (r"의왕", "경기 의왕시", GYEONGGI_2025),
    (r"하남시|경기\s*(?:도\s*)?하남", "경기 하남시", GYEONGGI_2025),
    (r"동탄", "화성시 동탄구", GYEONGGI_2026), (r"기흥", "용인시 기흥구", GYEONGGI_2026),
    (r"구리시|경기\s*(?:도\s*)?구리", "경기 구리시", GYEONGGI_2026),
]
# Cities only partly designated: the district decides.
PARTLY = {"수원": "수원시의 구(영통·장안·팔달은 2025-10-16부터 지정, 권선은 아님)",
          "용인": "용인시의 구(수지는 2025-10-16, 기흥은 2026-07-01부터 지정, 처인은 아님)",
          "안양": "안양시의 구(동안은 2025-10-16부터 지정, 만안은 아님)",
          "화성": "화성시의 구(동탄구는 2026-07-01부터 지정)"}
OTHER_PLACES = (r"부산|대구|인천|광주|대전|울산|세종|강원|충북|충청북도|충남|충청남도|전북|전라북도|전남|전라남도|경북|"
                r"경상북도|경남|경상남도|제주|고양|부천|남양주|안산|평택|시흥|파주|의정부|김포|군포|오산|이천|양주|안성|"
                r"포천|여주|동두천|가평|양평|연천|권선구|만안구|처인구")


@dataclass(frozen=True)
class Area:
    label: str
    record: list


@dataclass(frozen=True)
class NeedsDistrict:
    label: str


def find_area(text: str):
    """Area, NeedsDistrict (a city designated only in part), or None when no place is recognised."""
    found = {}
    seoul = re.search(r"서울", text)
    for gu in SEOUL_GU:
        if re.search(rf"(?<![가-힣]){gu}\s*구", text) and (seoul or gu not in SHARED_GU):
            found[f"서울 {gu}구"] = SEOUL_FOUR if gu in SEOUL_FOUR_GU else SEOUL_OTHERS
    for pattern, label, record in SPECIFIC:
        if re.search(pattern, text) and not (label == "경기 성남시" and any(k.startswith("성남시") for k in found)):
            found.setdefault(label, record)
    if not found:
        for city, label in PARTLY.items():
            if re.search(city, text):
                return NeedsDistrict(label)
        place = re.search(OTHER_PLACES, text)
        if place:
            found[place.group()] = ELSEWHERE
    records = {tuple(r) for r in found.values()}
    if len(records) != 1:
        return None   # nothing recognised, or two places that do not agree
    label = " · ".join(found)
    return Area(label, list(records.pop()))


def adjusted_during(area: Area, start: date, end: date):
    """True/False when the record covers [start, end] with one status, else None.

    Days after CHECKED_ON take the status in force on it (no later notice is known); callers say so.
    """
    if start > end:
        return None
    start, end = min(start, CHECKED_ON), min(end, CHECKED_ON)
    statuses = set()
    day = start
    for begin, until, status in area.record:
        if until <= day or begin > end:
            continue
        if begin > day:
            return None   # a gap the record does not cover
        statuses.add(status)
        day = until
        if day > end:
            break
    if day <= end or len(statuses) != 1:
        return None
    return statuses.pop()


ACQUIRED = re.compile(r"((?:19|20)\d{2})\s*(?:년|[.\-/])\s*(?:(\d{1,2})\s*(?:월|[.\-/])\s*(?:(\d{1,2})\s*일?)?)?"
                      r"(?:(?!팔|양도|매도|처분)[^.\n]){0,20}?(?:샀|사서|(?<![가-힣])산\s|구입|구매|취득|매수|분양\s*받)")


def acquisition_period(texts, transfer: date, holding_years):
    """(first, last) possible acquisition day: a stated date, else the sale date less the holding years."""
    import calendar
    for text in reversed(texts):
        stated = list(ACQUIRED.finditer(text))
        if len(stated) == 1:
            year, month, day = (int(g) if g else None for g in stated[0].groups())
            try:
                if day:
                    return date(year, month, day), date(year, month, day)
                if month:
                    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
                return date(year, 1, 1), date(year, 12, 31)
            except ValueError:
                return None
        if len(stated) > 1:
            return None
    if holding_years is None:
        return None
    try:
        # Held "N years" (rounded down): bought more than N but less than N+1 years before the sale.
        return transfer.replace(year=transfer.year - holding_years - 1), transfer.replace(year=transfer.year - holding_years)
    except ValueError:   # 29 February
        return (transfer.replace(month=2, day=28, year=transfer.year - holding_years - 1),
                transfer.replace(month=2, day=28, year=transfer.year - holding_years))


def acquired_in_adjusted_area(area, period):
    """(value, note) for the residence rule, or (None, what to ask)."""
    if period is None:
        return None, "취득 연월(조정대상지역 여부는 취득 당시를 기준으로 판단)"
    first, last = period
    if last < RESIDENCE_RULE_FROM:
        return False, ("2017년 8월 2일 이전에 취득한 주택이라 취득 당시 조정대상지역이었더라도 2년 거주 요건이 없는 것으로 "
                       "보았습니다(소득세법 시행령 부칙, 2017.9.19.).")
    if isinstance(area, NeedsDistrict):
        return None, f"주택이 있는 {area.label}"
    if area is None:
        return None, ("취득 당시 조정대상지역이었는지(예/아니오). 모르시면 주택 소재지(시·구)와 취득 연월을 알려주세요")
    status = adjusted_during(area, max(first, RESIDENCE_RULE_FROM), last)
    if status is None:
        return None, (f"{area.label} 주택의 취득 연월(그 기간에 조정대상지역 지정·해제가 있었거나 지정 이력을 확인하지 "
                      "못한 기간입니다) 또는 취득 당시 조정대상지역이었는지(예/아니오)")
    return status, (f"{area.label}는 취득 시기({first.isoformat()}~{last.isoformat()})에 "
                    + ("조정대상지역이어서 2년 거주 요건을 적용했습니다." if status else "조정대상지역이 아니어서 거주 요건 없이 판단했습니다.")
                    + f" 지정 이력은 {CHECKED_ON.isoformat()}에 확인한 국토교통부 지정·해제 공고 기준입니다." + _later(last))


def _later(last):
    return (f" {CHECKED_ON.isoformat()} 뒤의 지정·해제는 반영하지 못했습니다." if last > CHECKED_ON else "")


def adjusted_on_transfer(area, transfer):
    """(value, note) for the multi-home surcharge on the sale date (a date or its (first, last) span)."""
    first, last = transfer if isinstance(transfer, tuple) else (transfer, transfer)
    when = first.isoformat() if first == last else f"{first.isoformat()}~{last.isoformat()}"
    if isinstance(area, NeedsDistrict):
        return None, f"주택이 있는 {area.label}"
    if area is None:
        return None, "양도하는 주택이 양도일 현재 조정대상지역에 있는지(예/아니오). 모르시면 주택 소재지(시·구)를 알려주세요"
    status = adjusted_during(area, first, last)
    if status is None:
        return None, (f"{area.label} 주택이 양도일({when}) 현재 조정대상지역인지(예/아니오) — "
                      "그 기간에 지정·해제가 있었거나 지정 여부를 확인하지 못했습니다")
    return status, (f"{area.label}는 양도일({when}) 현재 조정대상지역" + ("입니다" if status else "이 아닙니다")
                    + f"({CHECKED_ON.isoformat()}에 확인한 국토교통부 지정·해제 공고 기준)." + _later(last))

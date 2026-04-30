"""
services/law_api_service.py — 국가법령정보 Open API 클라이언트

지원 기능:
- search_law(law_name): 법령명으로 법령 목록 검색
- get_law_detail(mst): 법령일련번호로 법령 원문 XML 조회

파싱: law_parser_service.parse_articles(raw_xml) 참조

API 문서: https://www.law.go.kr/LSO/openApi/openApiInfoPage.do
인증키 발급: https://www.law.go.kr/LSO/openApi/openApiIntroPage.do
"""
import asyncio
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from config import LAW_API_KEY

_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
_DETAIL_URL = "https://www.law.go.kr/DRF/lawService.do"
_TIMEOUT = 30.0


@dataclass
class LawSummary:
    """법령 검색 결과 단건."""
    mst: str               # 법령일련번호 (상세 조회 키)
    law_name: str          # 법령명한글
    law_type: str          # 법령종류명 (법률/대통령령/부령 등)
    promulgation_date: str # 공포일자 (YYYYMMDD)
    ministry: str          # 소관부처명


def _require_api_key() -> str:
    """API 키 존재 확인. 없으면 명확한 오류 발생."""
    if not LAW_API_KEY:
        raise ValueError(
            "LAW_API_KEY가 설정되지 않았습니다.\n"
            ".env 파일에 LAW_API_KEY=발급받은키 형태로 추가하세요.\n"
            "발급: https://www.law.go.kr/LSO/openApi/openApiIntroPage.do"
        )
    return LAW_API_KEY


def _parse_search_xml(xml_text: str) -> list[LawSummary]:
    """법령 검색 API XML 응답 파싱. (laws만 반환, 하위호환용)"""
    laws, _ = _parse_search_result(xml_text)
    return laws


def _parse_search_result(xml_text: str) -> tuple[list[LawSummary], int]:
    """
    법령 검색 API XML 응답 파싱.

    응답 구조 (law.go.kr 기준):
    <LawSearch>
      <totalCnt>N</totalCnt>
      <law>
        <법령일련번호>...</법령일련번호>
        <법령명한글>...</법령명한글>
        <법령종류명>...</법령종류명>
        <공포일자>...</공포일자>
        <소관부처명>...</소관부처명>
      </law>
    </LawSearch>

    Returns:
        (law_list, total_count)
    """
    root = ET.fromstring(xml_text)

    total_el = root.find("totalCnt")
    total_count = int(total_el.text.strip()) if total_el is not None and total_el.text else 0

    results: list[LawSummary] = []
    for law_el in root.findall("law"):
        def text(tag: str) -> str:
            el = law_el.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        results.append(LawSummary(
            mst=text("법령일련번호"),
            law_name=text("법령명한글"),
            law_type=text("법령종류명"),
            promulgation_date=text("공포일자"),
            ministry=text("소관부처명"),
        ))

    return results, total_count


async def search_law(
    law_name: str,
    *,
    display: int = 10,
    page: int = 1,
    exact: bool = False,
) -> list[LawSummary]:
    """
    법령명으로 법령 목록을 검색한다.

    Args:
        law_name: 검색할 법령명 (예: "소득세법")
        display:  한 페이지 결과 수 (최대 100)
        page:     페이지 번호 (1부터 시작)
        exact:    True이면 law_name 완전일치 항목만 필터링 (클라이언트 측 처리)

    Returns:
        LawSummary 리스트. 결과 없으면 빈 리스트.

    Raises:
        ValueError: API 키 미설정
        httpx.TimeoutException: 타임아웃
        httpx.HTTPStatusError: 4xx/5xx 응답
        ET.ParseError: 비정상 XML 응답
    """
    api_key = _require_api_key()

    params = {
        "OC":      api_key,
        "target":  "law",
        "type":    "XML",
        "query":   law_name,
        "display": str(display),
        "page":    str(page),
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_SEARCH_URL, params=params)
        resp.raise_for_status()

    laws = _parse_search_xml(resp.text)

    if exact:
        laws = [law for law in laws if law.law_name == law_name]

    return laws


async def search_law_all_pages(
    query: str,
    *,
    display: int = 100,
    max_results: int = 2000,
    request_delay: float = 0.3,
) -> list[LawSummary]:
    """
    법령명 키워드로 전체 결과를 페이지네이션하여 가져온다.

    Args:
        query:         검색 키워드
        display:       페이지당 결과 수 (최대 100)
        max_results:   최대 수집 건수 (API 부하 방지용 상한)
        request_delay: 페이지 요청 간 대기시간(초)

    Returns:
        LawSummary 리스트 (중복 MST 포함 가능 — 호출자가 de-dup)
    """
    api_key = _require_api_key()
    all_laws: list[LawSummary] = []
    page = 1

    while len(all_laws) < max_results:
        params = {
            "OC":      api_key,
            "target":  "law",
            "type":    "XML",
            "query":   query,
            "display": str(display),
            "page":    str(page),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()

        laws, total_count = _parse_search_result(resp.text)
        if not laws:
            break

        all_laws.extend(laws)

        fetched_so_far = (page - 1) * display + len(laws)
        if fetched_so_far >= min(total_count, max_results):
            break

        page += 1
        if request_delay > 0:
            await asyncio.sleep(request_delay)

    return all_laws


async def get_law_detail(mst: str) -> dict:
    """
    법령일련번호(MST)로 법령 원문 XML을 조회한다.

    Returns:
        {"mst": mst, "raw_xml": xml문자열}
        조문 파싱은 law_parser_service.parse_articles(raw_xml) 사용.


    """
    api_key = _require_api_key()

    params = {
        "OC":     api_key,
        "target": "law",
        "type":   "XML",
        "MST":    mst,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_DETAIL_URL, params=params)
        resp.raise_for_status()

    return {"mst": mst, "raw_xml": resp.text}

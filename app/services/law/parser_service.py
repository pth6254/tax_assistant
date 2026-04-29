"""
services/law_parser_service.py — 국가법령정보 API XML 조문 파싱

law_api_service.get_law_detail()이 반환한 raw_xml을 받아
조문 단위 LawArticle 리스트로 변환한다.

법령 XML 예상 구조 (law.go.kr):
  <법령>
    <기본정보>
      <법령명_한글>소득세법</법령명_한글>
      <법령종류명>법률</법령종류명>
      <시행일자>20260101</시행일자>
      <공포일자>20251231</공포일자>
    </기본정보>
    <조문>
      <조문단위>
        <조문번호>1</조문번호>
        <조문가지번호/>
        <조문여부>조문</조문여부>   <!-- "삭제"이면 건너뜀 -->
        <조문제목>목적</조문제목>
        <조문내용>이 법은...</조문내용>
        <항>
          <항번호>①</항번호>
          <항내용>...</항내용>
        </항>
      </조문단위>
    </조문>
  </법령>

주의: 태그명은 API 버전마다 다를 수 있으므로 방어적으로 파싱한다.
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class LawArticle:
    """조문 단위 파싱 결과."""
    law_name: str       # 법령명 (기본정보에서 추출)
    law_type: str       # 법령종류 (법률/대통령령/부령 등)
    article_no: str     # 조문번호 — 예: "제1조", "제3조의2"
    article_title: str  # 조문제목
    article_text: str   # 조문내용 + 항 내용 합산 (정규화)
    effective_date: str # 시행일자 (YYYYMMDD)
    amendment_date: str # 공포일자 (YYYYMMDD)


# ── 태그명 후보 정의 ─────────────────────────────────────────────
# API 버전이나 법령 종류에 따라 태그명이 달라질 수 있어 후보를 순서대로 시도한다.

_BASIC_TAG_CANDIDATES: dict[str, list[str]] = {
    "law_name":       ["법령명_한글", "법령명한글", "법령명"],
    "law_type":       ["법령종류명",  "법령종류",   "법종류"],
    "effective_date": ["시행일자"],
    "amendment_date": ["공포일자"],
}

_ARTICLE_SECTION_CANDIDATES = ["조문", "조문목록"]
_ARTICLE_UNIT_CANDIDATES    = ["조문단위", "조문"]
_ARTICLE_NO_TAGS            = ["조문번호"]
_ARTICLE_BRANCH_TAGS        = ["조문가지번호"]
_ARTICLE_STATUS_TAGS        = ["조문여부"]
_ARTICLE_TITLE_TAGS         = ["조문제목", "조제목"]
_ARTICLE_CONTENT_TAGS       = ["조문내용", "조내용"]
_PARA_UNIT_TAGS             = ["항"]
_PARA_CONTENT_TAGS          = ["항내용"]


def normalize_text(text: str) -> str:
    """
    텍스트 정규화:
    - 유니코드 공백/제어문자 제거 (ZWNJ, BOM 등)
    - 연속 공백/줄바꿈 정리
    - 앞뒤 공백 제거
    """
    if not text:
        return ""

    # 유니코드 정규화 (NFC)
    text = unicodedata.normalize("NFC", text)

    # 제로폭 공백 및 BOM 계열 제거
    text = re.sub(r"[​‌‍﻿­]", "", text)

    # 탭 → 공백
    text = text.replace("\t", " ")

    # 연속 공백 → 단일 공백
    text = re.sub(r" {2,}", " ", text)

    # 3개 이상 연속 줄바꿈 → 2개로
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 줄 단위로 앞뒤 공백 제거
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)

    return text.strip()


def _find_text(el: ET.Element, *tag_candidates: str) -> str:
    """여러 태그명 후보 중 텍스트가 있는 첫 번째를 반환한다."""
    for tag in tag_candidates:
        child = el.find(tag)
        if child is not None and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _find_element(el: ET.Element, *tag_candidates: str) -> ET.Element | None:
    """여러 태그명 후보 중 존재하는 첫 번째 Element를 반환한다."""
    for tag in tag_candidates:
        child = el.find(tag)
        if child is not None:
            return child
    return None


def _build_article_no(no: str, branch: str) -> str:
    """
    조문번호 + 조문가지번호 → 표준 조문번호 문자열.
    예: no="3", branch="2" → "제3조의2"
        no="1", branch=""  → "제1조"
    """
    if not no:
        return ""
    base = f"제{no}조"
    return f"{base}의{branch}" if branch else base


def _collect_para_text(article_el: ET.Element) -> str:
    """
    항 요소들의 내용을 모아 하나의 문자열로 반환한다.
    항/호/목 세분화 없이 항내용만 순서대로 합산한다.
    """
    parts: list[str] = []
    for para_tag in _PARA_UNIT_TAGS:
        for para_el in article_el.findall(para_tag):
            content = _find_text(para_el, *_PARA_CONTENT_TAGS)
            if content:
                parts.append(content)
    return "\n".join(parts)


def _parse_basic_info(root: ET.Element) -> dict[str, str]:
    """기본정보 섹션에서 법령명/종류/날짜를 추출한다."""
    # 기본정보 섹션 탐색 (없으면 루트에서 직접 읽기)
    basic_el = root.find("기본정보") or root

    result: dict[str, str] = {}
    for key, candidates in _BASIC_TAG_CANDIDATES.items():
        result[key] = _find_text(basic_el, *candidates)

    return result


def _parse_article_units(root: ET.Element) -> list[ET.Element]:
    """조문 섹션에서 조문단위 Element 목록을 추출한다."""
    # 조문 섹션 탐색
    section = _find_element(root, *_ARTICLE_SECTION_CANDIDATES)
    if section is None:
        return []

    units: list[ET.Element] = []
    for tag in _ARTICLE_UNIT_CANDIDATES:
        found = section.findall(tag)
        if found:
            units = found
            break

    return units


def parse_articles(
    raw_xml: str,
    *,
    law_name_hint: str = "",
    law_type_hint: str = "",
) -> list[LawArticle]:
    """
    법령 상세 XML을 파싱하여 조문 단위 LawArticle 리스트를 반환한다.

    Args:
        raw_xml:       get_law_detail()["raw_xml"]
        law_name_hint: XML에서 법령명을 못 읽을 때 사용할 대체값
        law_type_hint: XML에서 법령종류를 못 읽을 때 사용할 대체값

    Returns:
        LawArticle 리스트. 본문이 비어있는 조문은 제외.
        파싱 실패 시 빈 리스트 반환 (예외 전파 없음).
    """
    if not raw_xml or not raw_xml.strip():
        return []

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        print(f"[law_parser] XML 파싱 실패: {e}")
        return []

    # 기본정보 추출
    try:
        info = _parse_basic_info(root)
    except Exception as e:
        print(f"[law_parser] 기본정보 추출 실패: {e}")
        info = {}

    law_name       = info.get("law_name", "")       or law_name_hint
    law_type       = info.get("law_type", "")       or law_type_hint
    effective_date = info.get("effective_date", "")
    amendment_date = info.get("amendment_date", "")

    # 조문단위 추출
    try:
        units = _parse_article_units(root)
    except Exception as e:
        print(f"[law_parser] 조문 섹션 추출 실패: {e}")
        return []

    articles: list[LawArticle] = []
    for unit in units:
        try:
            # 삭제 조문 건너뜀
            status = _find_text(unit, *_ARTICLE_STATUS_TAGS)
            if status == "삭제":
                continue

            no     = _find_text(unit, *_ARTICLE_NO_TAGS)
            branch = _find_text(unit, *_ARTICLE_BRANCH_TAGS)
            title  = _find_text(unit, *_ARTICLE_TITLE_TAGS)

            # 조문 본문 = 조문내용 + 항 내용 합산
            direct_content = _find_text(unit, *_ARTICLE_CONTENT_TAGS)
            para_content   = _collect_para_text(unit)

            parts = [p for p in [direct_content, para_content] if p]
            article_text = normalize_text("\n".join(parts))

            # 본문이 비어있으면 제외
            if not article_text:
                continue

            articles.append(LawArticle(
                law_name=law_name,
                law_type=law_type,
                article_no=_build_article_no(no, branch),
                article_title=normalize_text(title),
                article_text=article_text,
                effective_date=effective_date,
                amendment_date=amendment_date,
            ))

        except Exception as e:
            print(f"[law_parser] 조문단위 파싱 실패 (건너뜀): {e}")
            continue

    return articles


def summarize_articles(articles: list[LawArticle]) -> None:
    """파싱 결과를 콘솔에 출력한다 (테스트/디버그용)."""
    if not articles:
        print("  파싱된 조문 없음")
        return

    first = articles[0]
    print(f"  법령명: {first.law_name} ({first.law_type})")
    print(f"  시행일: {first.effective_date} | 공포일: {first.amendment_date}")
    print(f"  총 조문 수: {len(articles)}")
    print()
    for a in articles[:5]:
        preview = a.article_text[:80].replace("\n", " ")
        print(f"  {a.article_no} [{a.article_title}]")
        print(f"    {preview}{'...' if len(a.article_text) > 80 else ''}")
    if len(articles) > 5:
        print(f"  ... 이하 {len(articles) - 5}개 생략")

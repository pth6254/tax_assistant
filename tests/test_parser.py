"""
test_parser.py — parser_service 단위 테스트

외부 의존성 없이 XML 파싱 로직만 검증한다.
"""
import pytest
from app.services.law.parser_service import (
    _build_article_no,
    normalize_text,
    parse_articles,
)

# ── normalize_text ───────────────────────────────────────────────

def test_normalize_text_strips_whitespace():
    assert normalize_text("  안녕  ") == "안녕"


def test_normalize_text_collapses_spaces():
    assert normalize_text("소득세  법") == "소득세 법"


def test_normalize_text_limits_newlines():
    result = normalize_text("a\n\n\n\nb")
    assert "\n\n\n" not in result


def test_normalize_text_empty_returns_empty():
    assert normalize_text("") == ""


def test_normalize_text_none_equivalent():
    assert normalize_text("   ") == ""


# ── _build_article_no ────────────────────────────────────────────

def test_build_article_no_simple():
    assert _build_article_no("1", "") == "제1조"


def test_build_article_no_with_branch():
    assert _build_article_no("3", "2") == "제3조의2"


def test_build_article_no_empty_returns_empty():
    assert _build_article_no("", "") == ""


# ── parse_articles ───────────────────────────────────────────────

_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
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
      <조문여부>조문</조문여부>
      <조문제목>목적</조문제목>
      <조문내용>이 법은 소득세에 관한 사항을 규정함을 목적으로 한다.</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>2</조문번호>
      <조문가지번호/>
      <조문여부>삭제</조문여부>
      <조문제목>삭제된 조문</조문제목>
      <조문내용>삭제</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>3</조문번호>
      <조문가지번호>2</조문가지번호>
      <조문여부>조문</조문여부>
      <조문제목>정의</조문제목>
      <조문내용>이 법에서 사용하는 용어의 뜻은 다음과 같다.</조문내용>
    </조문단위>
  </조문>
</법령>"""


def test_parse_articles_returns_list():
    result = parse_articles(_SAMPLE_XML)
    assert isinstance(result, list)


def test_parse_articles_skips_deleted():
    result = parse_articles(_SAMPLE_XML)
    article_nos = [a.article_no for a in result]
    assert "제2조" not in article_nos


def test_parse_articles_correct_count():
    result = parse_articles(_SAMPLE_XML)
    assert len(result) == 2


def test_parse_articles_law_name():
    result = parse_articles(_SAMPLE_XML)
    assert result[0].law_name == "소득세법"


def test_parse_articles_law_type():
    result = parse_articles(_SAMPLE_XML)
    assert result[0].law_type == "법률"


# 실제 국가법령정보 API(target=law) 응답은 "법령종류명"이 아니라 "법종구분" 태그를 사용한다
# (예: <법종구분 법령구분코드="A0002">법률</법종구분>). 이 태그명 불일치로 인해
# law_type이 항상 빈 문자열로 저장되던 실제 버그가 있었다 — 회귀 방지용 테스트.
_REAL_TAG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<법령 법령키="0015652025122321221">
  <기본정보>
    <법령명_한글><![CDATA[소득세법]]></법령명_한글>
    <법종구분 법종구분코드="A0002">법률</법종구분>
    <시행일자>20260101</시행일자>
    <공포일자>20251231</공포일자>
  </기본정보>
  <조문>
    <조문단위>
      <조문번호>1</조문번호>
      <조문가지번호/>
      <조문여부>조문</조문여부>
      <조문제목>목적</조문제목>
      <조문내용>이 법은 소득세에 관한 사항을 규정함을 목적으로 한다.</조문내용>
    </조문단위>
  </조문>
</법령>"""


def test_parse_articles_law_type_real_api_tag():
    result = parse_articles(_REAL_TAG_XML)
    assert result[0].law_type == "법률"


# 절/관/장 구조 표제는 <조문여부>전문</조문여부>으로 내려오며 다음 조문과 같은
# 조문번호를 공유한다. 과거 이를 걸러내지 않아 코퍼스의 12%가 표제 쓰레기 행이었음.
_HEADING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령명_한글>소득세법</법령명_한글>
    <법종구분>법률</법종구분>
    <시행일자>20260101</시행일자>
    <공포일자>20251231</공포일자>
  </기본정보>
  <조문>
    <조문단위>
      <조문번호>55</조문번호>
      <조문여부>전문</조문여부>
      <조문내용>제4절 세액의 계산 &lt;개정 2009.12.31&gt;</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>55</조문번호>
      <조문여부>전문</조문여부>
      <조문내용>제1관 세율 &lt;개정 2009.12.31&gt;</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>55</조문번호>
      <조문가지번호/>
      <조문여부>조문</조문여부>
      <조문제목>세율</조문제목>
      <조문내용>제55조(세율) ①거주자의 종합소득에 대한 소득세는...</조문내용>
    </조문단위>
  </조문>
</법령>"""


def test_parse_articles_skips_section_headings():
    """조문여부='전문'인 절/관 표제는 저장 대상에서 제외되어야 한다."""
    result = parse_articles(_HEADING_XML)
    assert len(result) == 1
    assert result[0].article_no == "제55조"
    assert result[0].article_title == "세율"
    assert result[0].article_text.startswith("제55조(세율)")


def test_parse_articles_empty_status_still_parsed():
    """조문여부 태그가 없는 XML 변형에서는 방어적으로 조문을 통과시킨다."""
    xml = _HEADING_XML.replace("<조문여부>조문</조문여부>", "")
    result = parse_articles(xml)
    # 표제 2개('전문')는 여전히 걸러지고, 태그 없는 실제 조문은 살아남아야 함
    assert len(result) == 1
    assert result[0].article_title == "세율"


def test_parse_articles_article_no_format():
    result = parse_articles(_SAMPLE_XML)
    assert result[0].article_no == "제1조"


def test_parse_articles_branch_no_format():
    result = parse_articles(_SAMPLE_XML)
    assert result[1].article_no == "제3조의2"


def test_parse_articles_dates():
    result = parse_articles(_SAMPLE_XML)
    assert result[0].effective_date == "20260101"
    assert result[0].amendment_date == "20251231"


def test_parse_articles_empty_xml_returns_empty():
    assert parse_articles("") == []


def test_parse_articles_invalid_xml_returns_empty():
    assert parse_articles("<broken xml") == []


def test_parse_articles_hint_fallback():
    xml_no_name = """<?xml version="1.0"?>
    <법령>
      <조문>
        <조문단위>
          <조문번호>1</조문번호>
          <조문가지번호/>
          <조문여부>조문</조문여부>
          <조문내용>내용</조문내용>
        </조문단위>
      </조문>
    </법령>"""
    result = parse_articles(xml_no_name, law_name_hint="법인세법", law_type_hint="법률")
    assert result[0].law_name == "법인세법"
    assert result[0].law_type == "법률"

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

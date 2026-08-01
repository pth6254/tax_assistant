"""조문 본문 항·호·목 추출과 실존 검증 테스트."""
from app.services.law.reference_parser import parse_law_reference
from app.services.law.structure_parser import resolve_reference_target, split_paragraphs

_ARTICLE = """제10조(지원 대상)
① 첫 번째 항의 본문이다.
1. 첫 번째 호의 본문이다.
가. 첫 번째 목의 본문이다.
나. 두 번째 목의 본문이다.
2. 두 번째 호의 본문이다.
② 두 번째 항의 본문이다.
1의2. 가지번호가 있는 호의 본문이다.
다. 세 번째 목의 본문이다."""


def test_split_paragraphs_keeps_short_and_single_units():
    paragraphs = split_paragraphs("제1조(목적)\n① 짧은 단일 항")
    assert len(paragraphs) == 1
    assert (paragraphs[0].number, paragraphs[0].label) == (1, "①")


def test_resolve_paragraph_text():
    target = resolve_reference_target(_ARTICLE, parse_law_reference("제10조 제2항"))
    assert target is not None and target.exists
    assert target.level == "paragraph"
    assert target.text.startswith("②")


def test_resolve_item_is_bounded_by_next_item():
    target = resolve_reference_target(_ARTICLE, parse_law_reference("제10조 제1항 제1호"))
    assert target is not None and target.exists
    assert "첫 번째 목" in target.text
    assert "두 번째 호" not in target.text


def test_resolve_item_branch_and_subitem():
    target = resolve_reference_target(
        _ARTICLE, parse_law_reference("제10조 제2항 제1호의2 다목")
    )
    assert target is not None and target.exists
    assert target.level == "subitem"
    assert target.text == "다. 세 번째 목의 본문이다."


def test_missing_paragraph_is_reported():
    target = resolve_reference_target(_ARTICLE, parse_law_reference("제10조 제9항"))
    assert target is not None and not target.exists
    assert target.level == "paragraph"
    assert "제9항" in target.detail


def test_missing_item_is_reported_within_paragraph():
    target = resolve_reference_target(_ARTICLE, parse_law_reference("제10조 제1항 제99호"))
    assert target is not None and not target.exists
    assert target.level == "item"


def test_article_without_paragraph_can_resolve_item():
    text = "제3조(요건) 다음 각 호에 해당한다.\n1. 첫 번째 요건\n2. 두 번째 요건"
    target = resolve_reference_target(text, parse_law_reference("제3조 제2호"))
    assert target is not None and target.exists
    assert target.text == "2. 두 번째 요건"


def test_article_only_reference_has_no_target():
    assert resolve_reference_target(_ARTICLE, parse_law_reference("제10조")) is None

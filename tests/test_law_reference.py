"""법령 조·항·호·목 참조 파서 테스트."""
import pytest

from app.services.law.reference_parser import (
    format_article_no,
    InvalidLawReference,
    extract_law_reference,
    normalize_article_no,
    paragraph_label_to_number,
    paragraph_number_to_label,
    parse_law_reference,
)


def test_article_branch_is_not_paragraph():
    reference = parse_law_reference("제59조의4")
    assert (reference.article, reference.article_branch, reference.paragraph) == (59, 4, None)
    assert reference.article_no == "제59조의4"


def test_format_article_no_is_canonical():
    assert format_article_no("059", "04") == "제59조의4"


def test_paragraph_is_not_article_branch():
    reference = parse_law_reference("제59조 제4항")
    assert (reference.article, reference.article_branch, reference.paragraph) == (59, None, 4)


def test_branch_article_and_paragraph_are_both_preserved():
    reference = parse_law_reference("제59조의4 제4항")
    assert (reference.article, reference.article_branch, reference.paragraph) == (59, 4, 4)
    assert reference.canonical == "제59조의4 제4항"


def test_full_law_reference():
    reference = parse_law_reference("소득세법 제59조의4 제9항 제1호 가목")
    assert (reference.law_name, reference.article, reference.article_branch) == ("소득세법", 59, 4)
    assert (reference.paragraph, reference.item, reference.subitem) == (9, 1, "가")
    assert reference.canonical == "소득세법 제59조의4 제9항 제1호 가목"


@pytest.mark.parametrize(
    ("value", "law_name"),
    [
        ("소득세법 시행령 제118조의5 제2항 제3호 나목", "소득세법 시행령"),
        ("소득세법 시행규칙 제58조의2 제1항 제4호 다목", "소득세법 시행규칙"),
    ],
)
def test_enforcement_decree_and_rule_reference(value, law_name):
    reference = parse_law_reference(value)
    assert reference.law_name == law_name
    assert reference.article_branch is not None
    assert reference.paragraph is not None
    assert reference.item is not None
    assert reference.subitem is not None


def test_extract_enforcement_decree_reference_from_question():
    reference = extract_law_reference(
        "소득세법 시행령 제118조의5 제2항 제3호 나목을 설명해줘"
    )
    assert reference is not None
    assert reference.law_name == "소득세법 시행령"
    assert reference.canonical == "소득세법 시행령 제118조의5 제2항 제3호 나목"


def test_circled_paragraph_is_normalized():
    reference = parse_law_reference("소득세법 제59조의4 ⑨")
    assert reference.paragraph == 9
    assert reference.paragraph_no == "제9항"
    assert reference.paragraph_label == "⑨"


def test_item_branch_is_distinct():
    reference = parse_law_reference("제10조 제2항 제3호의2 나목")
    assert (reference.item, reference.item_branch, reference.item_no) == (3, 2, "제3호의2")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("55", "제55조"),
        ("55조", "제55조"),
        ("제 55 조", "제55조"),
        ("59의4", "제59조의4"),
        ("59조의4", "제59조의4"),
        ("제 59 조 의 4", "제59조의4"),
    ],
)
def test_normalize_article_shorthand(raw, expected):
    assert normalize_article_no(raw) == expected


def test_interpretation_case_number_is_not_changed():
    assert normalize_article_no("11-0150") == "11-0150"


def test_extract_reference_from_question():
    reference = extract_law_reference("소득세법 제59조의4 제9항 제1호가 적용되나요?")
    assert reference is not None
    assert (reference.law_name, reference.article_no) == ("소득세법", "제59조의4")
    assert (reference.paragraph, reference.item) == (9, 1)


def test_paragraph_marker_conversion():
    assert paragraph_number_to_label(9) == "⑨"
    assert paragraph_label_to_number("⑨") == 9
    assert paragraph_number_to_label(36) is None


@pytest.mark.parametrize("value", ["", "소득세법", "제오십오조", "55-A"])
def test_invalid_reference_raises(value):
    with pytest.raises(InvalidLawReference):
        parse_law_reference(value)

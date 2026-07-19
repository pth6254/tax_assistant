"""
test_clause_splitter.py — 조문 항(項) 단위 분할 단위 테스트
"""
from app.services.law.clause_splitter import (
    build_clause_embed_text,
    should_split,
    split_into_clauses,
)

_LONG_ARTICLE = (
    "제59조의4(특별세액공제)\n"
    "① 근로소득이 있는 거주자가 보험료를 지급한 경우 그 금액의 100분의 12에 해당하는 금액을 세액공제한다. "
    + "보험료 세부 요건 설명이 이어진다. " * 25 + "\n"
    "② 의료비를 지급한 경우 그 금액의 100분의 15에 해당하는 금액을 공제한다. "
    + "의료비 세부 요건 설명이 이어진다. " * 25 + "\n"
    "⑨ 거주자가 다음 각 호의 어느 하나에 해당하는 경우 표준세액공제로 연 13만원을 공제한다. "
    + "표준세액공제 세부 요건 설명이 이어진다. " * 25
)


def test_split_returns_clauses_with_labels():
    clauses = split_into_clauses(_LONG_ARTICLE)
    labels = [label for label, _ in clauses]
    assert labels == ["①", "②", "⑨"]


def test_split_clause_text_starts_with_marker():
    clauses = split_into_clauses(_LONG_ARTICLE)
    for label, text in clauses:
        assert text.startswith(label)


def test_split_skips_tiny_clauses():
    """'③ 삭제 <2010.12.30>' 같은 짧은 항은 임베딩 대상에서 제외."""
    text = (
        "제10조(예시)\n"
        "① " + "실제 내용이 충분히 긴 항입니다. " * 5 + "\n"
        "② 삭제 <2010.12.30>\n"
        "③ " + "이것도 충분히 긴 항입니다. " * 5
    )
    labels = [label for label, _ in split_into_clauses(text)]
    assert labels == ["①", "③"]


def test_split_returns_empty_for_single_clause():
    text = "제1조(목적) 이 법은 소득세를 규정한다.\n① 유일한 항입니다." + "내용. " * 30
    assert split_into_clauses(text) == []


def test_split_returns_empty_for_no_clauses():
    assert split_into_clauses("제1조(목적) 항 구분이 없는 짧은 조문.") == []


def test_should_split_requires_min_length():
    """300자(CLAUSE_SPLIT_MIN_CHARS) 미만은 항이 여러 개라도 분할 대상이 아니다."""
    tiny = "제1조\n① 짧은 항.\n② 또 짧은 항."
    assert should_split(tiny) is False
    assert should_split(_LONG_ARTICLE) is True


def test_build_clause_embed_text_includes_context():
    text = build_clause_embed_text(
        "소득세법", "제59조의4", "특별세액공제", _LONG_ARTICLE, "⑨ 표준세액공제 내용"
    )
    assert "법령명: 소득세법" in text
    assert "제59조의4" in text
    assert "특별세액공제" in text
    assert "⑨ 표준세액공제 내용" in text
    # 조문 첫 줄(헤더)이 맥락으로 포함되어야 함
    assert "제59조의4(특별세액공제)" in text


def test_extended_circled_numbers_supported():
    """㉑ 이상의 원문자도 항 마커로 인식한다."""
    text = (
        "제100조(예시)\n"
        "⑳ " + "스무번째 항 내용. " * 10 + "\n"
        "㉑ " + "스물한번째 항 내용. " * 10
    )
    labels = [label for label, _ in split_into_clauses(text)]
    assert labels == ["⑳", "㉑"]

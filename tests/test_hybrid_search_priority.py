"""
test_hybrid_search_priority.py — law_type → (priority, source_type) 분류 단위 테스트

기존 tests/test_hybrid_search.py는 모듈 경로(app.services.law.hybrid_search_service)가
실제 경로(app.services.search.hybrid_search_service)와 달라 수집(collection) 단계에서부터
실패하는 상태라 pytest 실행에서 제외되어 있다. 이 파일은 그와 별개로 올바른 경로에서
_classify_law_type 하나만 검증한다.
"""
from app.services.search.hybrid_search_service import _classify_law_type


def test_classify_exact_law():
    priority, source_type = _classify_law_type("법률")
    assert priority == 0
    assert source_type == "law"


def test_classify_exact_presidential_decree():
    priority, source_type = _classify_law_type("대통령령")
    assert priority == 1
    assert source_type == "regulation"


def test_classify_exact_rule_types():
    for law_type in ("총리령", "부령"):
        priority, source_type = _classify_law_type(law_type)
        assert priority == 2
        assert source_type == "rule"


def test_classify_interpretation():
    priority, source_type = _classify_law_type("법령해석례")
    assert priority == 3
    assert source_type == "interpretation"


def test_classify_ministry_specific_rule_suffix():
    """'행정안전부령'·'재정경제부령'처럼 부처명이 붙은 부령은 '부령' 접미사로 분류돼야 한다."""
    for law_type in ("행정안전부령", "재정경제부령", "기획재정부령"):
        priority, source_type = _classify_law_type(law_type)
        assert priority == 2
        assert source_type == "rule"


def test_classify_unknown_falls_back_to_default():
    priority, source_type = _classify_law_type("알수없는유형")
    assert priority == 2
    assert source_type == "law"


def test_classify_empty_string_falls_back_to_default():
    priority, source_type = _classify_law_type("")
    assert priority == 2
    assert source_type == "law"

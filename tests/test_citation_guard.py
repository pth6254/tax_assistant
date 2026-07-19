"""
test_citation_guard.py — 답변 인용/계산 수치 검증 후처리 단위 테스트
"""
from app.services.citation_guard import (
    apply_citation_guard,
    build_citation_footer,
    extract_citations,
    verify_calc_final_amount,
    verify_citations,
)

_CONTEXT = (
    "[출처: 소득세법 | 소득세법 | 📌 법률 (law)]\n"
    "제55조 [세율]\n소득세는 다음 각 호의 세율을 적용한다..."
)


# ── extract_citations ────────────────────────────────────────────

def test_extract_single_citation():
    answer = "## 법적 근거\n[법률] 소득세법 제55조 - 세율\n"
    assert extract_citations(answer) == [("법률", "소득세법", "제55조")]


def test_extract_multiple_citations_mixed_types():
    answer = (
        "[법률] 소득세법 제55조 - 세율\n"
        "[시행령] 소득세법 시행령 제47조\n"
        "[시행규칙] 부가가치세법 시행규칙 제9조\n"
    )
    result = extract_citations(answer)
    assert ("법률", "소득세법", "제55조") in result
    assert ("시행령", "소득세법 시행령", "제47조") in result
    assert ("시행규칙", "부가가치세법 시행규칙", "제9조") in result


def test_extract_no_citations():
    assert extract_citations("법령 인용이 전혀 없는 답변입니다.") == []


def test_extract_ignores_web_source():
    """[웹출처]는 법령 인용 패턴이 아니므로 추출되지 않는다."""
    assert extract_citations("[웹출처] https://nts.go.kr") == []


def test_extract_spaced_article_number_normalized():
    """모델이 '제 50 조'처럼 공백을 섞어 출력해도 표준형 '제50조'로 추출된다.

    (qwen 계열 토크나이저 특성 — 실제 답변에서 관찰된 형식. 과거 엄격한 패턴은
    이런 인용을 전부 놓쳐 검증이 조용히 무력화됐다.)
    """
    answer = "**[법률] 소득세법 제 50 조 (기본공제)**: 연 150만원을 공제한다."
    assert extract_citations(answer) == [("법률", "소득세법", "제50조")]


def test_extract_spaced_article_with_branch_normalized():
    """'제 59 조의 4' 같은 가지번호 공백 변형도 '제59조의4'로 정규화된다."""
    answer = "[법률] 소득세법 제 59 조의 4 - 특별세액공제"
    assert extract_citations(answer) == [("법률", "소득세법", "제59조의4")]


def test_extract_spaced_law_name():
    """공백 포함 법령명('상속세 및 증여세법')도 통째로 추출된다."""
    answer = "[법률] 상속세 및 증여세법 제18조 - 기초공제"
    assert extract_citations(answer) == [("법률", "상속세 및 증여세법", "제18조")]


def test_extract_strips_markdown_bold_from_law_name():
    """'**[법률] 소득세법 제50조**'처럼 볼드로 감싼 인용에서 마커가 법령명에 섞이지 않는다."""
    answer = "*   **[법률] 소득세법 제50조 (기본공제)**: 연 150만원을 공제한다."
    citations = extract_citations(answer)
    assert citations[0][1] == "소득세법"
    assert citations[0][2] == "제50조"


def test_verify_spaced_citation_against_context():
    """공백 변형 인용도 컨텍스트 대조 검증이 정상 동작해야 한다."""
    answer = "**[법률] 소득세법 제 55 조 (세율)**에 따라 과세된다."
    checks = verify_citations(answer, _CONTEXT)
    assert len(checks) == 1
    assert checks[0].verified is True
    assert checks[0].article_no == "제55조"


# ── verify_citations ──────────────────────────────────────────────

def test_verify_citation_found_in_context():
    answer = "[법률] 소득세법 제55조 - 세율"
    checks = verify_citations(answer, _CONTEXT)
    assert len(checks) == 1
    assert checks[0].verified is True


def test_verify_citation_not_found_is_flagged():
    answer = "[법률] 소득세법 제999조 - 존재하지 않는 조문"
    checks = verify_citations(answer, _CONTEXT)
    assert checks[0].verified is False


def test_verify_citation_wrong_law_name_flagged():
    """조문번호는 맞지만 법령명이 다르면 미검증 처리."""
    answer = "[법률] 부가가치세법 제55조"
    checks = verify_citations(answer, _CONTEXT)
    assert checks[0].verified is False


def test_verify_citation_ignores_whitespace_difference():
    """'상속세및증여세법' vs '상속세 및 증여세법' 같은 공백 차이는 무시한다."""
    context = "제53조 [증여재산 공제]\n상속세 및 증여세법 관련 조문"
    answer = "[법률] 상속세및증여세법 제53조 - 증여재산공제"
    checks = verify_citations(answer, context)
    assert checks[0].verified is True


# ── verify_calc_final_amount ──────────────────────────────────────

def test_verify_calc_amount_present():
    calc_context = "세목: 소득세\n- 과세표준: 48,500,000원\n- 결정세액: 5,895,000원"
    answer = "결정세액은 5,895,000원입니다."
    assert verify_calc_final_amount(answer, calc_context) is True


def test_verify_calc_amount_missing_flagged():
    calc_context = "세목: 소득세\n- 과세표준: 48,500,000원\n- 결정세액: 5,895,000원"
    answer = "결정세액은 대략 6,200,000원 정도로 추정됩니다."
    assert verify_calc_final_amount(answer, calc_context) is False


def test_verify_calc_amount_no_calc_context_passes():
    """계산기가 실행되지 않았으면(None) 검증 대상이 없으므로 통과."""
    assert verify_calc_final_amount("아무 답변", None) is True


# ── build_citation_footer / apply_citation_guard ──────────────────

def test_footer_empty_when_all_verified():
    answer = "[법률] 소득세법 제55조 - 세율"
    assert build_citation_footer(answer, _CONTEXT) == ""


def test_footer_added_when_unverified_citation():
    answer = "[법률] 소득세법 제999조 - 존재하지 않는 조문"
    footer = build_citation_footer(answer, _CONTEXT)
    assert "제999조" in footer
    assert "확인되지" in footer


def test_footer_added_when_calc_mismatch():
    calc_context = "- 결정세액: 5,895,000원"
    answer = "세금은 6,200,000원 나올 것으로 보입니다."
    footer = build_citation_footer(answer, _CONTEXT, calc_context)
    assert "계산기 결과" in footer


def test_apply_citation_guard_appends_footer():
    answer = "[법률] 소득세법 제999조"
    result = apply_citation_guard(answer, _CONTEXT)
    assert result.startswith(answer)
    assert "확인되지" in result


def test_apply_citation_guard_no_change_when_clean():
    answer = "[법률] 소득세법 제55조 - 세율"
    assert apply_citation_guard(answer, _CONTEXT) == answer


def test_footer_added_when_context_has_source_but_answer_has_no_citation():
    """검색 컨텍스트가 있는데 답변이 인용을 하나도 달지 않으면(템플릿 이탈) 경고가 붙는다."""
    answer = "중소기업은 여러 요건을 갖추면 세액감면을 받을 수 있습니다."
    footer = build_citation_footer(answer, _CONTEXT)
    assert "인용이 없습니다" in footer


def test_footer_empty_when_no_context_and_no_citation():
    """검색된 법령 자료 자체가 없으면(잡담 등) 인용이 없어도 경고를 붙이지 않는다."""
    answer = "안녕하세요! 무엇을 도와드릴까요?"
    assert build_citation_footer(answer, "관련 문서를 찾지 못했습니다.") == ""

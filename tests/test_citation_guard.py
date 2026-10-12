"""
test_citation_guard.py — 주장 인용이 연결한 공식 근거의 법령·조문·항과 일치하는지 확인
"""
from app.services.citation_guard import verify_citations
from app.services.evidence import context_from_records, digest, record_from_result
from tests.test_reliability_workflow import source


def evidence(*rows):
    """Official records as retrieval returns them: (law_name, article_no, category, body)."""
    records = []
    for n, (law, article, category, body) in enumerate(rows):
        text = f"{article}\n{body}"
        records.append(record_from_result(source(law_name=law, article_no=article, category=category,
                                                  content=text, original_text=text, source_id=str(n),
                                                  content_hash=digest(text))))
    return context_from_records(records)


INCOME = evidence(("소득세법", "제55조", "법률", "① 거주자의 종합소득에 대한 소득세는 기본세율을 적용한다."))


def test_a_spaced_article_number_is_matched():
    checks = verify_citations("**[법률] 소득세법 제 55 조 (세율)**에 따라 과세된다.", INCOME)
    assert [(c.article_no, c.verified) for c in checks] == [("제55조", True)]


def test_an_article_that_was_not_retrieved_is_flagged():
    assert verify_citations("[법률] 소득세법 제999조", INCOME)[0].verified is False


def test_the_same_number_of_another_law_is_flagged():
    assert verify_citations("[법률] 부가가치세법 제55조", INCOME)[0].verified is False


def test_spacing_in_a_law_name_is_ignored():
    gift = evidence(("상속세 및 증여세법", "제53조", "법률", "① 증여재산 공제"))
    assert verify_citations("[법률] 상속세및증여세법 제53조", gift)[0].verified is True


def test_other_laws_partial_articles_and_missing_paragraphs_are_rejected():
    ctx = evidence(("소득세법", "제1조", "법률", "① 본문"), ("법인세법", "제2조", "법률", "① 본문"),
                   ("소득세법", "제59조의4", "법률", "① 본문"))
    for answer in ("[법률] 소득세법 제2조", "[법률] 소득세법 제59조", "[법률] 소득세법 제1조 제99항"):
        assert verify_citations(answer, ctx)[0].verified is False, answer
    assert verify_citations("[법률] 소득세법 제1조 제1항", ctx)[0].verified is True


def test_a_ministerial_rule_counts_as_an_enforcement_rule():
    ctx = evidence(("소득세법 시행규칙", "제1조", "기획재정부령", "본문"))
    assert verify_citations("[시행규칙] 소득세법 시행규칙 제1조", ctx)[0].verified is True


def test_a_label_that_does_not_match_the_source_kind_is_flagged():
    assert verify_citations("[시행령] 소득세법 제55조", INCOME)[0].verified is False


def test_no_citation_means_no_check():
    assert verify_citations("세율은 원문을 확인하세요.", INCOME) == []

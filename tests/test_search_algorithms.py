"""Behavioral cases: typos, polarity, reference boundaries and scoped diversity."""
import pytest
from unittest.mock import AsyncMock

from app.services.search.fuzzy_terms import expand_fuzzy_terms, one_edit_apart
from app.services.search.query_constraints import extract_constraints, canonical_law
from app.services.search.diversity import mmr_order
from app.services.search import hybrid_search_service as hybrid
from tests.test_reliability_workflow import source
from app.services.evidence import digest
from app.schemas.law import LawArticleDetail


@pytest.mark.parametrize('left,right', [('종합소득새','종합소득세'), ('세금계서','세금계산서'),
                                       ('세금계산서서','세금계산서'), ('abcd','abdc')])
def test_single_edit_including_transposition(left, right):
    assert one_edit_apart(left, right)
    assert one_edit_apart(right, left)
    assert not one_edit_apart(left, left)
    assert not one_edit_apart('abc', 'xyz')


def test_fuzzy_preserves_user_text_and_only_adds_unique_dictionary_terms():
    query = '종합소득새 신고 시 매입세액공재를 받을 수 있나요?'
    expanded, terms = expand_fuzzy_terms(query)
    assert expanded.startswith(query)
    assert terms == ['종합소득세', '매입세액공제']
    assert expand_fuzzy_terms('종합소득세를 신고합니다')[1] == []


def test_fuzzy_cannot_turn_disallowance_into_allowance_or_change_values():
    query = '2025년 부가가치세법 제39조 제1항 800만원 매입세액불공제'
    assert expand_fuzzy_terms(query) == (query, [])
    assert '매입세액공제' not in expand_fuzzy_terms('매입세액불공재')[1]
    assert expand_fuzzy_terms('면새 공재 법인새')[1] == []  # short ambiguous words remain unchanged


def test_regex_keeps_article_branch_paragraph_and_multiple_law_names_separate():
    result = extract_constraints('소득세법 제59조의4 제9항과 부가가치세법 제39조 제1항 원문 알려줘')
    assert [(r.law_name,r.article_no,r.paragraph) for r in result.references] == [
        ('소득세법','제59조의4',9), ('부가가치세법','제39조',1)]
    assert result.lookup_only
    assert canonical_law('가짜법') == '가짜법'
    assert canonical_law('상증세법 시행령') == '상속세 및 증여세법 시행령'


def test_regex_does_not_consume_analysis_or_infer_calculation_intent():
    result = extract_constraints('2025년 귀속 소득을 2026년에 신고합니다. 1억 원의 금융소득과 소득세법 제55조를 비교해서 설명해줘')
    assert result.date_count == 2
    assert not result.lookup_only
    assert extract_constraints('소득세법 제55조에 뭐라고 되어 있는지 알려줘').lookup_only
    assert not extract_constraints('소득세법 제55조 기준으로 세금 얼마나 낼까?').lookup_only


@pytest.mark.parametrize('name', ['가짜소득세법', '법인새법', '가짜상증세법'])
def test_unknown_law_name_cannot_be_promoted_to_a_known_law(name):
    query = f'{name} 제55조 원문 보여줘'
    result = extract_constraints(query)
    assert result.references[0].law_name == name
    assert result.lookup_only
    assert expand_fuzzy_terms(query) == (query, [])


def test_quoted_reference_preserves_exact_law_and_branch():
    result = extract_constraints('「소득세법 시행령」 제59조의4 제2항 원문 보여줘')
    assert result.lookup_only
    assert result.references[0].law_name == '소득세법 시행령'
    assert result.references[0].article_no == '제59조의4'


def test_mmr_leaves_order_unchanged_without_enough_valid_vectors():
    rows = [source(article_no=f'제{i+1}조', source_id=str(i+1)) for i in range(4)]
    assert mmr_order(rows, {}, pinned={('법인세법', '제4조')}) == rows


def test_mmr_keeps_required_pins_and_every_exception_but_moves_redundant_candidates():
    rows = [source(article_no=f'제{i+1}조', source_id=str(i+1)) for i in range(5)]
    vectors = {'1':[1,0,0], '2':[1,0,0], '3':[1,0,0], '4':[0,0,1], '5':[0,1,0]}
    ordered = mmr_order(rows, vectors, pinned={(rows[4].law_name, rows[4].article_no)}, lambda_mult=0.8)
    assert {r.source_id for r in ordered} == {'1','2','3','4','5'}
    assert [r.source_id for r in ordered[:2]] == ['1','2']
    assert ordered[4].source_id == '5'  # a late protected supplement stays late
    assert ordered.index(rows[3]) < ordered.index(rows[2])
    assert len(ordered) == len(rows)


@pytest.mark.asyncio
async def test_reference_only_request_avoids_similar_law_and_article_candidates(monkeypatch):
    article = LawArticleDetail(law_name='소득세법', law_type='법률', tax_type='소득세법',
        article_no='제55조',article_title='세율',article_text='제55조 공식 본문',effective_date='20260101',
        amendment_date='20260101',source_url='https://www.law.go.kr/',source_id='17',
        content_hash=digest('제55조 공식 본문'))
    lookup = AsyncMock(return_value=article)
    dense = AsyncMock(side_effect=AssertionError('must-not-search'))
    monkeypatch.setattr(hybrid, 'get_law_article', lookup)
    monkeypatch.setattr(hybrid, 'embed_texts', dense)
    diagnostic = {}
    hits = await hybrid.hybrid_search(['소득세법 제55조 내용'], original_query='소득세법 제55조 원문 알려줘',
                                    official_only=True, issue_mode=True, diagnostics=diagnostic)
    assert [(r.law_name,r.article_no) for r in hits] == [('소득세법','제55조')]
    dense.assert_not_awaited()
    assert diagnostic['exact_reference_route']

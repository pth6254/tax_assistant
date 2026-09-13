from unittest.mock import AsyncMock

import pytest

from app.services.graph.index_service import article_key, build_graph
from app.services.law.relation_extractor import extract_relations
from app.services.search import graph_search_service as service
from app.services.search.hybrid_search_service import _row_to_article_result, format_hybrid_context
from app.schemas.law import LawArticleDetail


def article(number='제1조', text='제1조(목적) 본문', law='시험법'):
    return dict(law_name=law, article_no=number, article_title='', article_text=text,
                law_type='법률', tax_type='시험', effective_date='20260101',
                amendment_date='20260101', source_url='https://example.test/law')


def test_explicit_references_and_branches():
    refs = extract_relations('「소득세법 시행령」 제59조의4 제2항 제1호의2 가목에 따른다.')
    assert refs[0]['law_name'] == '소득세법 시행령'
    assert refs[0]['article_no'] == '제59조의4'
    assert refs[0]['reference'] == '제59조의4 제2항 제1호의2 가목'


@pytest.mark.parametrize('text', ['같은 법 제3조', '법 제3조', '제3조',
    '「시험법」 제3조부터 제5조까지', '구 「시험법」 제3조', '종전의 「시험법」 제3조'])
def test_ambiguous_historical_and_ranges_not_inferred(text):
    assert extract_relations(text) == []


def test_graph_resolution_and_missing_subdivision():
    source = article(text='「시험법」 제2조 및 「시험법」 제2조 제9항, 「없는법」 제1조')
    target = article('제2조', '제2조(요건) ① 내용')
    nodes, edges, unresolved = build_graph([source, target])
    assert len(nodes) == 2
    assert len(edges) == 1
    assert unresolved == 2
    assert edges[0]['target'] == article_key(target)
    assert build_graph([source, target]) == (nodes, edges, unresolved)
    assert article_key(target | {'amendment_date': '20260201'}) != article_key(target)


def test_unknown_and_future_effective_dates_excluded():
    assert build_graph([article() | {'effective_date': ''}])[0] == []
    assert build_graph([article() | {'effective_date': '29990101'}])[0] == []


def test_ordinary_words_after_citation_are_not_subitem_labels():
    assert extract_relations('「시험법」 제1조 종목')[0]['reference'] == '제1조'


@pytest.mark.asyncio
async def test_historical_query_does_not_expand(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    expand = AsyncMock()
    monkeypatch.setattr(service, '_expand', expand)
    results = [object()]
    assert await service.expand_graph(results, '2024년 기준') is results
    expand.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_never_connects(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', False)
    query = AsyncMock()
    monkeypatch.setattr(service, 'neighbors', query)
    results = [_row_to_article_result(article() | {'similarity_score': 1})]
    assert await service.expand_graph(results) is results
    query.assert_not_called()


@pytest.mark.asyncio
async def test_expansion_and_stale_target(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    source = article(text='「시험법」 제2조에 따른다.')
    target = article('제2조', '제2조 본문')
    results = [_row_to_article_result(source | {'similarity_score': 1})]
    lookup = AsyncMock(side_effect=lambda law, number: LawArticleDetail(**(source if number == '제1조' else target)))
    monkeypatch.setattr(service, 'get_law_article', lookup)
    edge = dict(source_key=article_key(source), target_key=article_key(target),
                law_name='시험법', article_no='제2조', evidence='「시험법」 제2조')
    monkeypatch.setattr(service, 'neighbors', AsyncMock(return_value=[edge, edge]))
    expanded = await service.expand_graph(results)
    assert len(expanded) == 2
    assert expanded[0] is results[0]
    assert expanded[1].similarity_score == 0
    assert '관계 검색 보조 근거' in format_hybrid_context(expanded)
    edge['target_key'] = 'obsolete-version'
    assert await service.expand_graph(results) == results


@pytest.mark.asyncio
async def test_failure_and_timeout_keep_base_results(monkeypatch):
    import asyncio
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    results = [object()]
    monkeypatch.setattr(service, '_expand', AsyncMock(side_effect=RuntimeError('private')))
    assert await service.expand_graph(results) is results
    async def slow(_):
        await asyncio.sleep(10)
    monkeypatch.setattr(service, '_expand', slow)
    monkeypatch.setattr(service.config, 'GRAPH_TIMEOUT_SEC', 0.01)
    assert await service.expand_graph(results) is results


@pytest.mark.asyncio
async def test_pdf_never_becomes_graph_seed(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    result = _row_to_article_result(article() | {'similarity_score': 1})
    result.article_no = ''
    query = AsyncMock()
    monkeypatch.setattr(service, 'neighbors', query)
    assert await service.expand_graph([result]) == [result]
    query.assert_not_called()


@pytest.mark.asyncio
async def test_changed_source_does_not_traverse(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    row = article()
    results = [_row_to_article_result(row | {'similarity_score': 1})]
    monkeypatch.setattr(service, 'get_law_article', AsyncMock(return_value=
        LawArticleDetail(**(row | {'article_text': 'changed'}))))
    query = AsyncMock()
    monkeypatch.setattr(service, 'neighbors', query)
    assert await service.expand_graph(results) == results
    query.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed(monkeypatch):
    import asyncio
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    monkeypatch.setattr(service, '_expand', AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await service.expand_graph([object()])

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
async def test_expansion_logs_counts_without_query(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    base = [object()]
    expanded = base + [object()]
    monkeypatch.setattr(service, '_expand', AsyncMock(return_value=expanded))
    with caplog.at_level(logging.INFO, logger=service.__name__):
        assert await service.expand_graph(base, 'private query') is expanded
    assert 'base=1 added=1' in caplog.text
    assert 'private query' not in caplog.text


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
    async def slow(_, query=''):
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


def test_alias_requires_definition_and_matching_family():
    base = article('제2조', '제2조 대상')
    definition = article(text='「시험법」(이하 "법"이라 한다)에 따른다.', law='시험법 시행령')
    source = article('제3조', '법 제2조에 따른다.', law='시험법 시행령')
    nodes, edges, _ = build_graph([base, definition, source])
    assert len(edges) == 1
    assert edges[0]['target'] == article_key(base)
    assert edges[0]['alias_definition_key'] == article_key(definition)
    assert build_graph([base, source])[1] == []
    assert build_graph([base, definition | {'article_text': '「다른법」(이하 "법"이라 한다)'}, source])[1] == []


def test_alias_shadowing_and_same_law_not_guessed():
    base = article('제2조', '제2조 대상')
    definition = article(text='「시험법」(이하 "법"이라 한다)', law='시험법 시행령')
    source = article('제3조', '같은 법 제2조와 종전의 법 제2조', law='시험법 시행령')
    assert build_graph([base, definition, source])[1] == []
    source['article_text'] = '법 제2조'
    shadow = article('제4조', '「다른법」(이하 이 조에서 "법"이라 한다)', law='시험법 시행령')
    assert build_graph([base, definition, source, shadow])[1] == []


def test_alias_defined_later_applies_only_after_definition():
    base = article('제2조', '제2조 대상')
    definition = article('제3조', '법 제2조. 「시험법」(이하 "법"이라 한다). 법 제2조.', law='시험법 시행령')
    before = article('제1조', '법 제2조.', law='시험법 시행령')
    after = article('제4조', '법 제2조.', law='시험법 시행령')
    edges = build_graph([base, before, definition, after])[1]
    assert len(edges) == 2
    assert {e['source'] for e in edges} == {article_key(definition), article_key(after)}
    assert all(e['alias_definition_article'] == '제3조' for e in edges)


@pytest.mark.asyncio
async def test_incoming_relevance_and_alias_version_guard(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    source = article(text='제1조 의료비 공제')
    target = article('제2조', '제2조 의료비 공제 요건')
    result = _row_to_article_result(source | {'similarity_score': 1})
    monkeypatch.setattr(service, 'get_law_article', AsyncMock(side_effect=lambda law, number:
        LawArticleDetail(**(source if number == '제1조' else target))))
    edge = dict(source_key=article_key(source), target_key=article_key(target),
                law_name='시험법', article_no='제2조', evidence='「시험법」 제1조', direction='incoming')
    monkeypatch.setattr(service, 'neighbors', AsyncMock(return_value=[edge]))
    assert len(await service.expand_graph([result], '의료비 공제')) == 2
    assert len(await service.expand_graph([result], '주택 양도')) == 1
    edge.update(alias_definition_key='old', alias_definition_law='시험법')
    assert len(await service.expand_graph([result], '의료비 공제')) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('queries', [['의료비'], ['의료비', '공제']])
async def test_normal_search_calls_graph_after_base_ranking(monkeypatch, queries):
    from app.services.search import hybrid_search_service as hybrid
    result = _row_to_article_result(article() | {'similarity_score': 1})
    monkeypatch.setattr(hybrid, '_lookup_referenced_article', AsyncMock(return_value=None))
    monkeypatch.setattr(hybrid, 'embed_texts', AsyncMock(return_value=[[0.0]] * len(queries)))
    monkeypatch.setattr(hybrid, '_search_all', AsyncMock(return_value=[result]))
    expand = AsyncMock(return_value=[result])
    monkeypatch.setattr(hybrid, 'expand_graph', expand)
    assert await hybrid.hybrid_search(queries, original_query='의료비 공제') == [result]
    expand.assert_awaited_once_with([result], '의료비 공제')


@pytest.mark.asyncio
async def test_reverse_other_family_and_large_context_excluded(monkeypatch):
    monkeypatch.setattr(service.config, 'GRAPH_RAG_ENABLED', True)
    source = article()
    target = article('제2조', '의료비 공제', law='다른법')
    base = [_row_to_article_result(source | {'similarity_score': 1})]
    monkeypatch.setattr(service, 'get_law_article', AsyncMock(side_effect=lambda law, number:
        LawArticleDetail(**(source if number == '제1조' else target))))
    edge = dict(source_key=article_key(source), target_key=article_key(target), law_name='다른법',
                article_no='제2조', evidence='「시험법」 제1조', direction='incoming')
    monkeypatch.setattr(service, 'neighbors', AsyncMock(return_value=[edge]))
    assert await service.expand_graph(base, '의료비 공제') == base
    target['article_text'] = '의료비 공제' * 1000
    edge.update(direction='outgoing', target_key=article_key(target))
    assert await service.expand_graph(base, '의료비 공제') == base

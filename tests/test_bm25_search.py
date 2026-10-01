"""BM25 behavior, source freshness and independent hybrid failure boundaries."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.search.bm25 import BM25Index, BM25Fields
from app.services.search import bm25_search_service as lexical
from app.services.search import hybrid_search_service as hybrid
from app.services.search import query_embedding_cache as cache
from app.services.search.korean_analyzer import analyze_query
from app.services.evidence import digest
from tests.conftest import _make_mock_pool
from tests.test_reliability_workflow import source


def test_bm25_rare_terms_length_normalization_and_tf_saturation():
    index = BM25Index([['tax'] * 100 + ['refund'], ['tax', 'refund'], ['tax', 'other']])
    hits = index.search(['refund'])
    assert [hit.index for hit in hits] == [1, 0]
    assert index.idf['refund'] > index.idf['tax']
    assert index.search(['refund', 'refund']) == hits
    repeated = BM25Index([['tax'], ['tax'] * 100], b=0)
    scores = {hit.index: hit.score for hit in repeated.search(['tax'])}
    assert 1 < scores[1] / scores[0] < 3


def test_bm25_scope_is_applied_before_top_k_and_empty_cases():
    index = BM25Index([['tax'], ['tax', 'refund'], ['refund']])
    assert [hit.index for hit in index.search(['refund'], 1, {1})] == [1]
    assert index.search(['refund'], 1, set()) == []
    assert index.search(['unknown']) == []
    assert BM25Index([]).search(['tax']) == []


def test_title_match_is_not_diluted_by_a_long_legal_body():
    index = BM25Fields([['refund'], ['other']],
                       [['refund'] + ['conditions'] * 300, ['refund']], title_weight=2)
    assert [hit.index for hit in index.search(['refund'])] == [0, 1]
    assert [hit.index for hit in index.search(['refund'], allowed={1})] == [1]


def test_fusion_preserves_branch_scores_without_mixing_with_cosine():
    vector = source(similarity_score=0.7, retrieval_scores={'vector': 0.7})
    lexical_hit = source(similarity_score=0, retrieval_scores={'bm25': 14.0})
    hits = hybrid._fuse_issue_rankings([[vector], [lexical_hit]], 2, k=10, weights=[1, 0.5])
    assert hits[0].similarity_score == 0.7
    assert hits[0].retrieval_scores == {'vector': 0.7, 'bm25': 14.0, 'rrf': 1.5 / 11}
    assert 'rrf' not in vector.retrieval_scores


def test_dense_leader_rescue_is_bounded_and_does_not_promote_interpretations():
    primary = [source(article_no='해석례', source_type='interpretation'),
               source(article_no='제1조'), source(article_no='제2조'), source(article_no='제3조')]
    fused = [source(article_no='제9조')]
    hits, added = hybrid._preserve_dense_leaders(fused, primary)
    assert hits[0] is fused[0]
    assert [row.article_no for row in added] == ['제1조', '제2조']


def test_tracing_outputs_do_not_include_source_bodies_or_depend_on_wrapper_shape():
    row = source()
    direct = hybrid._retrieval_outputs([row])
    assert direct == hybrid._retrieval_outputs({'output': [row]})
    assert row.content not in str(direct)


@pytest.mark.asyncio
async def test_refined_query_law_alias_resolves_the_same_official_original(monkeypatch):
    from app.schemas.law import LawArticleDetail
    article = LawArticleDetail(law_name='상속세 및 증여세법', article_no='제53조',
        article_title='증여재산공제', article_text='제53조 본문', law_type='법률',
        tax_type='상속세 및 증여세법', effective_date='20260101', amendment_date='20260101',
        source_url='https://www.law.go.kr/', source_id='17', content_hash=digest('제53조 본문'))
    lookup = AsyncMock(return_value=article)
    monkeypatch.setattr(hybrid, 'get_law_article', lookup)
    hit = await hybrid._lookup_referenced_article(
        '성년 자녀 상속세 및 증여세법 공제 한도 및 요건(상증세법 제53조)', '상속세 및 증여세법')
    lookup.assert_awaited_once_with('상속세 및 증여세법', '제53조')
    assert hit.source_id == '17'
    assert hybrid._canonical_lookup_law('부가세법 시행령') == '부가가치세법 시행령'
    assert hybrid._canonical_lookup_law('가짜상증세법') == '가짜상증세법'


def test_korean_analyzer_preserves_compounds_particles_and_article_branches():
    assert '매입세액' in analyze_query('매입세액을 공제받을 수 있나요?')
    assert 'ref:59:4' in analyze_query('소득세법 제 59 조의 4 제9항')
    assert '부가가치세' in analyze_query('부가세 신고')
    assert '배우자' in analyze_query('배우자에게 증여할 때')


@pytest.mark.asyncio
async def test_embedding_cache_deduplicates_and_keeps_model_version_separate(monkeypatch):
    cache.clear_query_embedding_cache()
    embed = AsyncMock(return_value=[[1, 2]])
    assert await cache.cached_embed_queries(['question', 'question'], embedder=embed) == [[1, 2], [1, 2]]
    await cache.cached_embed_queries(['question'], embedder=embed)
    assert embed.call_count == 1
    monkeypatch.setattr(cache.config, 'EMBEDDING_VERSION', 'different')
    await cache.cached_embed_queries(['question'], embedder=embed)
    assert embed.call_count == 2
    cache.clear_query_embedding_cache()


@pytest.mark.asyncio
async def test_embedding_cache_does_not_cache_failed_batches():
    cache.clear_query_embedding_cache()
    embed = AsyncMock(side_effect=[RuntimeError('offline'), [[1, 2]]])
    with pytest.raises(RuntimeError):
        await cache.cached_embed_queries(['failure'], embedder=embed)
    assert await cache.cached_embed_queries(['failure'], embedder=embed) == [[1, 2]]
    assert embed.call_count == 2


@pytest.mark.asyncio
async def test_bm25_rechecks_current_source_before_returning_it(monkeypatch):
    row = dict(id=17, law_name='시험법', article_no='제1조', article_title='요건',
               article_text='제1조 업무 조건', content_hash=digest('제1조 업무 조건'),
               tax_type='시험법', law_type='법률', source_url='https://www.law.go.kr/',
               effective_date='20260101', amendment_date='20260101')
    index = lexical.Snapshot(('revision',), (row | {'parent_id': 17},), {17: row['content_hash']},
                             BM25Index([['업무']]), {'시험법': {0}}, 0.1)
    monkeypatch.setattr(lexical, '_snapshot', index)
    monkeypatch.setattr(lexical, '_checked_at', float('inf'))
    monkeypatch.setattr(lexical, '_indexed_invalidation', lexical._invalidation)
    pool, conn = _make_mock_pool()
    conn.fetch.return_value = [row]
    monkeypatch.setattr(lexical, 'get_pool', AsyncMock(return_value=pool))
    hits = await lexical.search_bm25_articles('업무', '시험법', 1)
    assert len(hits) == 1 and hits[0].retrieval_scores['bm25'] > 0
    assert hits[0].content_hash == row['content_hash']
    conn.fetch.return_value = [row | {'content_hash': 'changed'}]
    assert await lexical.search_bm25_articles('업무', '시험법', 1) == []
    assert lexical._checked_at == 0


@pytest.mark.asyncio
async def test_embedding_singleflight_survives_a_cancelled_waiter():
    cache.clear_query_embedding_cache()
    started, release = asyncio.Event(), asyncio.Event()
    async def embed(texts):
        started.set()
        await release.wait()
        return [[1, 2]]
    embedder = AsyncMock(side_effect=embed)
    first = asyncio.create_task(cache.cached_embed_queries(['shared'], embedder=embedder))
    await started.wait()
    second = asyncio.create_task(cache.cached_embed_queries(['shared'], embedder=embedder))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == [[1, 2]]
    assert embedder.call_count == 1
    cache.clear_query_embedding_cache()


@pytest.mark.asyncio
async def test_bm25_rejects_same_text_with_changed_tax_scope(monkeypatch):
    row = dict(id=17, law_name='시험법', article_no='제1조', article_title='요건',
               article_text='제1조 업무 조건', content_hash=digest('제1조 업무 조건'),
               tax_type='시험법', law_type='법률', source_url='https://www.law.go.kr/',
               effective_date='20260101', amendment_date='20260101')
    snapshot = lexical.Snapshot(('revision',), (row | {'parent_id': 17},), {17: row['content_hash']},
                                BM25Index([['업무']]), {'시험법': {0}}, 0.1)
    monkeypatch.setattr(lexical, '_snapshot', snapshot)
    monkeypatch.setattr(lexical, '_checked_at', float('inf'))
    monkeypatch.setattr(lexical, '_indexed_invalidation', lexical._invalidation)
    monkeypatch.setattr(lexical, '_invalidation', lexical._invalidation)
    pool, conn = _make_mock_pool()
    conn.fetch.return_value = [row | {'tax_type': '다른법'}]
    monkeypatch.setattr(lexical, 'get_pool', AsyncMock(return_value=pool))
    assert await lexical.search_bm25_articles('업무', '시험법', 1) == []


@pytest.mark.asyncio
async def test_invalidated_bm25_rebuilds_even_when_db_revision_is_unchanged(monkeypatch):
    revision = (0, None, lexical.ANALYZER_VERSION, lexical.config.SEARCH_BM25_TITLE_WEIGHT,
                lexical.date.today().isoformat())
    old = lexical.Snapshot(revision, (), {}, BM25Index([]), {}, 0)
    monkeypatch.setattr(lexical, '_snapshot', old)
    monkeypatch.setattr(lexical, '_invalidation', 1)
    monkeypatch.setattr(lexical, '_indexed_invalidation', 0)
    monkeypatch.setattr(lexical, '_checked_at', 0)
    pool, conn = _make_mock_pool()
    conn.fetchrow.return_value = {'count': 0, 'updated': None}
    conn.fetch.return_value = []
    monkeypatch.setattr(lexical, 'get_pool', AsyncMock(return_value=pool))
    assert await lexical._refresh() is not old
    assert lexical._indexed_invalidation == 1
    conn.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_dense_failure_does_not_block_bm25_evidence(monkeypatch):
    cache.clear_query_embedding_cache()
    monkeypatch.setattr(hybrid.config, 'SEARCH_LEXICAL_BACKEND', 'bm25')
    monkeypatch.setattr(hybrid, 'embed_texts', AsyncMock(side_effect=RuntimeError('offline')))
    monkeypatch.setattr(hybrid, 'search_bm25_articles', AsyncMock(return_value=[source()]))
    monkeypatch.setattr(hybrid, 'expand_graph', AsyncMock(side_effect=lambda rows, _: rows))
    detail = {}
    hits = await hybrid.hybrid_search(['query'], official_only=True, issue_mode=True, diagnostics=detail)
    assert len(hits) == 1
    assert detail['vector_error'] == 'RuntimeError'
    assert detail['lexical_backend'] == 'bm25'


@pytest.mark.asyncio
async def test_lexical_failure_uses_trigram_without_blocking_dense(monkeypatch):
    cache.clear_query_embedding_cache()
    monkeypatch.setattr(hybrid.config, 'SEARCH_LEXICAL_BACKEND', 'bm25')
    monkeypatch.setattr(hybrid, 'embed_texts', AsyncMock(return_value=[[1, 2]]))
    monkeypatch.setattr(hybrid, '_search_law_articles', AsyncMock(return_value=[source()]))
    monkeypatch.setattr(hybrid, 'search_bm25_articles', AsyncMock(side_effect=RuntimeError('offline')))
    fallback = AsyncMock(return_value=[])
    monkeypatch.setattr(hybrid, '_search_keyword_articles', fallback)
    monkeypatch.setattr(hybrid, 'expand_graph', AsyncMock(side_effect=lambda rows, _: rows))
    detail = {}
    assert await hybrid.hybrid_search(['query'], official_only=True, issue_mode=True, diagnostics=detail)
    assert detail['bm25_error'] == 'RuntimeError'
    assert detail['lexical_backend'] == 'trigram'
    fallback.assert_awaited_once()

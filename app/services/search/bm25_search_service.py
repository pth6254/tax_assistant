"""Read-only BM25 index derived from verified current official law originals.

PostgreSQL owns source data. Each process holds a replaceable sparse index; it
checks a corpus revision periodically and rechecks every selected source at read
time. No user uploads enter this shared index. A failed refresh retains the old
index, but stale/changed rows cannot be returned as evidence.
"""
import asyncio
from dataclasses import dataclass
from datetime import date
import logging
import time

import config
from app.database import get_pool
from app.services.evidence import digest
from app.services.graph.index_service import effective_now
from app.services.law.source_recovery import recover_article, has_missing_items
from app.services.search.bm25 import BM25Fields
from app.services.search.korean_analyzer import ANALYZER_VERSION, analyze_many, analyze_query

logger = logging.getLogger(__name__)
_COLUMNS = '''id, content_hash, law_name, law_type, tax_type, article_no,
    article_title, article_text, source_url, effective_date, amendment_date'''
_REVISION = '''SELECT count(*) AS count, max(updated_at)::text AS updated
    FROM law_articles WHERE is_current=TRUE AND law_type <> '법령해석례' '''
_LOAD = f'''SELECT DISTINCT ON (law_name, article_no) {_COLUMNS}
    FROM law_articles WHERE is_current=TRUE AND law_type <> '법령해석례'
      AND article_no <> ''
    ORDER BY law_name, article_no, (article_text LIKE article_no || '%') DESC,
             length(article_text) DESC, updated_at DESC, id DESC'''
_snapshot = None
_refresh_task = None
_checked_at = 0.0
_invalidation = 0
_indexed_invalidation = -1
_SOURCE_METADATA = ('law_name', 'law_type', 'tax_type', 'article_no', 'article_title',
                    'source_url', 'effective_date', 'amendment_date')


@dataclass(frozen=True)
class Snapshot:
    revision: tuple
    rows: tuple
    parent_hashes: dict
    index: BM25Fields
    scopes: dict
    built_seconds: float


def _build(rows, revision, parent_hashes, started):
    texts = [row['article_title'] for row in rows] + [row['article_text'] for row in rows]
    tokens = analyze_many(texts)
    scopes = {}
    for index, row in enumerate(rows):
        scopes.setdefault(row['tax_type'], set()).add(index)
    index = BM25Fields(tokens[:len(rows)], tokens[len(rows):], config.SEARCH_BM25_TITLE_WEIGHT)
    return Snapshot(revision, tuple(rows), parent_hashes, index, scopes,
                    time.perf_counter() - started)


async def _refresh():
    global _snapshot, _checked_at, _indexed_invalidation
    started = time.perf_counter()
    invalidation = _invalidation
    pool = await get_pool()
    async with pool.acquire() as conn:
        revision_row = await conn.fetchrow(_REVISION)
        revision = (revision_row['count'], revision_row['updated'], ANALYZER_VERSION,
                    config.SEARCH_BM25_TITLE_WEIGHT, date.today().isoformat())
        if (_snapshot is not None and revision == _snapshot.revision
                and invalidation == _indexed_invalidation):
            _checked_at = time.monotonic()
            return _snapshot
        raw_rows = await conn.fetch(_LOAD)
        rows, parents = [], {}
        for record in raw_rows:
            if not effective_now(record):
                continue
            row = await recover_article(record, conn)
            if (digest(row['article_text']) != row['content_hash']
                    or has_missing_items(row['article_text'])):
                continue
            parent = dict(row) | {'parent_id': record['id']}
            rows.append(parent)
            parents[record['id']] = record['content_hash']
    replacement = await asyncio.to_thread(_build, rows, revision, parents, started)
    # A single completed replacement is published; no partial index is visible.
    _snapshot = replacement
    _indexed_invalidation = invalidation
    _checked_at = time.monotonic()
    logger.info('[BM25] index ready articles=%d terms=%d seconds=%.3f analyzer=%s',
                len(rows), len(replacement.index.body.postings), replacement.built_seconds, ANALYZER_VERSION)
    return replacement


def _start_refresh():
    global _refresh_task
    if (_refresh_task is None or _refresh_task.done()
            or _refresh_task.get_loop() is not asyncio.get_running_loop()):
        _refresh_task = asyncio.create_task(_refresh())
        def completed(task):
            if not task.cancelled() and task.exception():
                logger.warning('[BM25] refresh unavailable (%s)', type(task.exception()).__name__)
        _refresh_task.add_done_callback(completed)
    return _refresh_task


async def warm_bm25_index():
    return await asyncio.shield(_start_refresh())


async def close_bm25_index():
    global _snapshot, _refresh_task, _checked_at, _invalidation, _indexed_invalidation
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        await asyncio.gather(_refresh_task, return_exceptions=True)
    _snapshot, _refresh_task, _checked_at = None, None, 0.0
    _invalidation, _indexed_invalidation = 0, -1


def invalidate_bm25_index():
    global _checked_at, _invalidation
    _checked_at = 0.0
    _invalidation += 1


async def search_bm25_articles(query, law_filter, top_k, diagnostics=None):
    global _checked_at
    from app.services.search.hybrid_search_service import _row_to_article_result
    if _snapshot is None:
        async with asyncio.timeout(12):
            snapshot = await warm_bm25_index()
    else:
        snapshot = _snapshot
        if (_invalidation != _indexed_invalidation
                or time.monotonic() - _checked_at >= config.SEARCH_BM25_REFRESH_SEC):
            _start_refresh()
    terms = await asyncio.to_thread(analyze_query, query)
    allowed = None if law_filter == 'ALL' else snapshot.scopes.get(law_filter, set())
    hits = snapshot.index.search(terms, top_k, allowed)
    ids = [snapshot.rows[hit.index]['parent_id'] for hit in hits]
    if diagnostics is not None:
        diagnostics['bm25_analyzer'] = ANALYZER_VERSION
        diagnostics['bm25_title_weight'] = config.SEARCH_BM25_TITLE_WEIGHT
        diagnostics['bm25_corpus_articles'] = len(snapshot.rows)
        diagnostics['bm25_index_build_seconds'] = round(snapshot.built_seconds, 3)
    if not ids:
        return []
    pool = await get_pool()
    results = []
    async with pool.acquire() as conn:
        fresh = {row['id']: row for row in await conn.fetch(
            f'SELECT {_COLUMNS} FROM law_articles WHERE is_current=TRUE AND id=ANY($1::bigint[])', ids)}
        for hit in hits:
            indexed = snapshot.rows[hit.index]
            row = fresh.get(indexed['parent_id'])
            if not row or row['content_hash'] != snapshot.parent_hashes[indexed['parent_id']]:
                invalidate_bm25_index()
                continue
            row = await recover_article(row, conn)
            if (row['content_hash'] != indexed['content_hash']
                    or any(row.get(key) != indexed.get(key) for key in _SOURCE_METADATA)
                    or digest(row['article_text']) != row['content_hash'] or not effective_now(row)):
                invalidate_bm25_index()
                continue
            result = _row_to_article_result(dict(row) | {'similarity_score': 0.0})
            result.retrieval_scores['bm25'] = hit.score
            results.append(result)
    if diagnostics is not None:
        diagnostics['bm25_ids'] = [(row.law_name, row.article_no) for row in results]
        diagnostics['bm25_scores'] = [round(row.retrieval_scores['bm25'], 4) for row in results]
    return results

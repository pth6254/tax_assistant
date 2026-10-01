"""A failed or concurrent clause reindex must preserve the existing index."""
from unittest.mock import AsyncMock

import pytest

from app.services.law import ingestion_service as ingestion
from app.services import embedding_service
from tests.conftest import _make_mock_pool
from tests.test_ingestion import _make_article


def article_and_parent():
    article = _make_article('제1조(목적)\n① ' + '첫째 요건 설명. ' * 100
                            + '\n② ' + '둘째 요건 설명. ' * 100)
    parent = vars(article) | {'id': 17, 'content_hash': ingestion._make_hash(article.article_text)}
    return article, parent


@pytest.mark.asyncio
async def test_embedding_failure_never_deletes_existing_clauses(monkeypatch):
    article, _ = article_and_parent()
    pool, conn = _make_mock_pool()
    monkeypatch.setattr(ingestion, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(embedding_service, 'embed_texts_for_storage',
                        AsyncMock(side_effect=RuntimeError('offline')))
    with pytest.raises(RuntimeError):
        await ingestion.embed_clauses_for_articles([(article, 17)])
    conn.execute.assert_not_called()
    conn.executemany.assert_not_called()


@pytest.mark.asyncio
async def test_changed_parent_never_deletes_existing_clauses(monkeypatch):
    article, parent = article_and_parent()
    pool, conn = _make_mock_pool()
    conn.fetch.return_value = [parent | {'content_hash': 'different'}]
    monkeypatch.setattr(ingestion, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(embedding_service, 'embed_texts_for_storage',
                        AsyncMock(return_value=([[1, 2], [3, 4]], None)))
    with pytest.raises(ValueError, match='clause_parent_changed'):
        await ingestion.embed_clauses_for_articles([(article, 17)])
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_insert_failure_exits_transaction_with_error(monkeypatch):
    article, parent = article_and_parent()
    pool, conn = _make_mock_pool()
    conn.fetch.return_value = [parent]
    conn.executemany.side_effect = RuntimeError('write_failed')
    monkeypatch.setattr(ingestion, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(embedding_service, 'embed_texts_for_storage',
                        AsyncMock(return_value=([[1, 2], [3, 4]], None)))
    with pytest.raises(RuntimeError):
        await ingestion.embed_clauses_for_articles([(article, 17)])
    assert conn.transaction.return_value.__aexit__.await_args.args[0] is RuntimeError


@pytest.mark.asyncio
async def test_successful_replacement_locks_matching_parent_in_transaction(monkeypatch):
    article, parent = article_and_parent()
    pool, conn = _make_mock_pool()
    conn.fetch.return_value = [parent]
    monkeypatch.setattr(ingestion, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(embedding_service, 'embed_texts_for_storage',
                        AsyncMock(return_value=([[1, 2], [3, 4]], None)))
    assert await ingestion.embed_clauses_for_articles([(article, 17)]) == 2
    assert 'FOR UPDATE' in conn.fetch.await_args.args[0]
    conn.transaction.return_value.__aenter__.assert_awaited_once()
    conn.executemany.assert_awaited_once()

"""Bounded cache of query embeddings, keyed by the actual embedding settings."""
import asyncio
from collections import OrderedDict
import time

import config
from app.services.embedding_service import embed_texts

_cache = OrderedDict()
_pending = {}


def _complete_batch(batch_key, task):
    if _pending.get(batch_key) is task:
        _pending.pop(batch_key, None)
    # A cancelled caller may leave shared work running. Retrieve its exception
    # even if there is no remaining waiter; failed batches still never enter cache.
    if not task.cancelled():
        task.exception()


def clear_query_embedding_cache():
    _cache.clear()


async def cached_embed_queries(texts, *, embedder=None, diagnostics=None):
    provider_key = (config.EMBEDDING_PROVIDER, config.EMBEDDING_BASE_URL,
                    config.EMBEDDING_MODEL, config.EMBEDDING_VERSION)
    now = time.monotonic()
    values, missing, hits = {}, [], 0
    for text in dict.fromkeys(texts):
        key = (provider_key, text)
        item = _cache.get(key)
        if item and now - item[0] < config.SEARCH_EMBED_CACHE_TTL_SEC:
            _cache.move_to_end(key)
            values[text] = item[1]
            hits += 1
        else:
            _cache.pop(key, None)
            missing.append(text)
    if missing:
        batch_key = (provider_key, tuple(missing))
        task = _pending.get(batch_key)
        if task is None or task.get_loop() is not asyncio.get_running_loop():
            task = asyncio.create_task((embedder or embed_texts)(missing))
            _pending[batch_key] = task
            task.add_done_callback(lambda done: _complete_batch(batch_key, done))
        vectors = await asyncio.shield(task)
        if len(vectors) != len(missing):
            raise ValueError('query_embedding_count_mismatch')
        for text, vector in zip(missing, vectors):
            values[text] = tuple(vector)
            _cache[(provider_key, text)] = (time.monotonic(), tuple(vector))
        while len(_cache) > config.SEARCH_EMBED_CACHE_SIZE:
            _cache.popitem(last=False)
    if diagnostics is not None:
        diagnostics['embedding_cache_hits'] = hits
        diagnostics['embedding_cache_misses'] = len(missing)
    return [list(values[text]) for text in texts]

"""Fail-open, one-hop expansion from verified official-law seeds."""
import asyncio
import logging
import re

import config
from app.services.graph.index_service import article_key, effective_now
from app.services.graph.store import neighbors
from app.services.law.lookup_service import get_law_article

logger = logging.getLogger(__name__)


async def expand_graph(results, query=''):
    if not config.GRAPH_RAG_ENABLED or not results:
        return results
    # This index is current-law only, not an as-of-date legal engine.
    if re.search(r'\d{4}\s*년|\d{4}[-./]\d|과거|종전|개정\s*전|당시', query):
        return results
    try:
        return await asyncio.wait_for(_expand(results), config.GRAPH_TIMEOUT_SEC)
    except Exception as error:
        # No raw driver exceptions: these may include credentials or query data.
        logger.warning('[GRAPH] expansion unavailable (%s); base results retained', type(error).__name__)
        return results


async def _expand(results):
    from app.services.search.hybrid_search_service import _row_to_article_result

    seeds = {}
    for result in results[:3]:
        if not result.article_no:  # PDF results are never graph seeds.
            continue
        article = await get_law_article(result.law_name, result.article_no)
        if article and effective_now(article.model_dump()):
            header = article.article_no + (f' [{article.article_title}]' if article.article_title else '')
            if result.content == f'{header}\n{article.article_text}':
                seeds[article_key(article.model_dump())] = article
    if not seeds:
        return results
    edges = await neighbors(list(seeds))
    seen = {(r.law_name, r.article_no) for r in results if r.article_no}
    additions = []
    for edge in edges:
        if edge['source_key'] not in seeds:
            continue
        identity = (edge['law_name'], edge['article_no'])
        if identity in seen:
            continue
        article = await get_law_article(*identity)
        if (not article or not effective_now(article.model_dump())
                or article_key(article.model_dump()) != edge['target_key']):
            continue  # Removed/changed graph targets cannot become evidence.
        row = article.model_dump() | {'similarity_score': 0.0}
        result = _row_to_article_result(row)
        result.graph_evidence = edge['evidence']
        additions.append(result)
        seen.add(identity)
        if len(additions) == 2:
            break
    return results + additions

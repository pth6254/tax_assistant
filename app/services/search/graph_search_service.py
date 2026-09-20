"""Fail-open, one-hop expansion from verified official-law seeds."""
import asyncio
import logging
import re

import config
from app.services.graph.index_service import article_key, effective_now
from app.services.graph.store import neighbors
from app.services.law.lookup_service import get_law_article

logger = logging.getLogger(__name__)
_MAX_ADDED_CHARS = 4000


async def expand_graph(results, query=''):
    if not config.GRAPH_RAG_ENABLED or not results:
        return results
    # This index is current-law only, not an as-of-date legal engine.
    if re.search(r'\d{4}\s*년|\d{4}[-./]\d|과거|종전|개정\s*전|당시', query):
        return results
    try:
        expanded = await asyncio.wait_for(_expand(results, query), config.GRAPH_TIMEOUT_SEC)
        logger.info('[GRAPH] expansion completed base=%d added=%d', len(results), len(expanded) - len(results))
        return expanded
    except Exception as error:
        # No raw driver exceptions: these may include credentials or query data.
        logger.warning('[GRAPH] expansion unavailable (%s); base results retained', type(error).__name__)
        return results


def relevance(query, article):
    """Cheap conservative lexical gate; not a semantic reranker score."""
    tokens = set(re.findall(r'[가-힣]{2,}', query))
    tokens = {re.sub(r'(?:에서는|에서|으로|은|는|을|를|의|과|와|도)$', '', t) for t in tokens}
    tokens -= {'법', '조', '항', '호', '시행령', '시행규칙', '알려줘', '알려주세요', '설명', '관련',
               '따른', '대해', '법률', '기준', '무엇', '어떻게', '뭐라고', '되어', '있는지', '내용', '궁금해',
               '얼마인가요', '되나요', '어떤', '경우', '언제', '하나요'}
    tokens -= set(re.findall(r'[가-힣]{2,}', article.law_name))
    tokens = {t for t in tokens if len(t) >= 2}
    return sum(2 if t in article.article_title else 1 for t in tokens if t in article.article_title or t in article.article_text)


async def _expand(results, query=''):
    from app.services.search.hybrid_search_service import _row_to_article_result

    seeds = {}
    for result in results[:3]:
        if not result.article_no or result.source_type == 'interpretation':
            continue
        article = await get_law_article(result.law_name, result.article_no)
        if article and effective_now(article.model_dump()):
            header = article.article_no + (f' [{article.article_title}]' if article.article_title else '')
            if result.content == f'{header}\n{article.article_text}':
                seeds[article_key(article.model_dump())] = article
    if not seeds:
        return results
    edges = await neighbors(list(seeds), bidirectional=True)
    seen = {(r.law_name, r.article_no) for r in results if r.article_no}
    additions = []
    verified_definitions = {}
    for edge in edges:
        if edge['source_key'] not in seeds:
            continue
        identity = (edge['law_name'], edge['article_no'])
        if identity in seen:
            continue
        seed = seeds[edge['source_key']]
        if edge.get('direction') == 'incoming':
            family = lambda name: re.sub(r'\s*시행(?:령|규칙)$', '', name).replace(' ', '')
            if family(identity[0]) != family(seed.law_name):
                continue  # A cross-family citation alone is not query relevance.
        article = await get_law_article(*identity)
        if (not article or not effective_now(article.model_dump())
                or article_key(article.model_dump()) != edge['target_key']):
            continue  # Removed/changed graph targets cannot become evidence.
        proof_key = edge.get('alias_definition_key')
        if proof_key:
            proof_law = edge.get('alias_definition_law')
            proof_identity = (proof_law, edge.get('alias_definition_article') or '제1조')
            if proof_identity not in verified_definitions:
                proof = await get_law_article(*proof_identity)
                verified_definitions[proof_identity] = article_key(proof.model_dump()) if proof else ''
            if verified_definitions[proof_identity] != proof_key:
                continue
        score = relevance(query, article)
        if query and score < (2 if edge.get('direction') == 'incoming' else 1):
            continue
        row = article.model_dump() | {'similarity_score': 0.0}
        result = _row_to_article_result(row)
        direction = '이 조문이 시작 조문을 인용' if edge.get('direction') == 'incoming' else '시작 조문에서 인용'
        result.graph_evidence = f'{seed.law_name} {seed.article_no} → {direction}: {edge["evidence"]}'
        additions.append((score, result))
        seen.add(identity)
    additions.sort(key=lambda pair: -pair[0])
    selected, chars = [], 0
    for _, result in additions:
        if chars + len(result.content) > _MAX_ADDED_CHARS:
            continue  # Do not silently truncate legal conditions mid-article.
        selected.append(result)
        chars += len(result.content)
        if len(selected) == 2:
            break
    return results + selected

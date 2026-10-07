"""
services/search/hybrid_search_service.py — 하이브리드 RAG 검색

law_articles(공식 법령 조문)와 documents(PDF 업로드) 두 테이블을
동시에 벡터 검색하고 우선순위에 따라 병합하여 LLM 컨텍스트를 생성한다.

우선순위 (낮을수록 높은 우선순위):
  0 — 법률         (law_articles, law_type=법률)
  1 — 시행령        (law_articles, law_type=대통령령)
  2 — 시행규칙      (law_articles, law_type=총리령/부령)
  3 — 유권해석      (law_articles, law_type=법령해석례) / 법령 PDF (documents, category=법령)
  4 — 시행령 PDF    (documents, category=시행령)
  5 — 시행규칙 PDF  (documents, category=시행규칙)
  6 — 집행기준      (documents, category=집행기준)
  7 — 기타 PDF      (documents, category=기타)

공개 법령(law_articles)은 모든 사용자에게 검색 가능.
사용자 업로드 PDF(documents)는 user_id 기준으로 격리하여 현재 로그인 사용자의 문서만 검색 가능.
"""
import asyncio
import logging
import re
import time
import uuid as _uuid
from dataclasses import replace
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
import config

from app.database import get_pool
from app.schemas.law import HybridSearchResult
from app.services.evidence import context_from_records, record_from_result, digest
from app.services.evidence import has_missing_items
from app.services.embedding_service import embed_texts
from app.services.law.reference_parser import extract_law_reference
from app.services.law.lookup_service import get_law_article
from app.services.search.graph_search_service import expand_graph
from app.services.search.bm25_search_service import search_bm25_articles
from app.services.search.query_embedding_cache import cached_embed_queries
from app.services.search.query_constraints import extract_constraints
from app.services.search.fuzzy_terms import expand_fuzzy_terms
from app.services.search.diversity import mmr_order
from config import EMBEDDING_VERSION, SIMILARITY_THRESHOLD, TOP_K

logger = logging.getLogger(__name__)
ISSUE_TITLE_RESCUE = True
_LAW_NAME_ALIASES = {'상증세법': '상속세 및 증여세법', '부가세법': '부가가치세법',
                     '조특법': '조세특례제한법', '국기법': '국세기본법'}


def _canonical_lookup_law(name):
    """Expand a bounded law-name alias, never arbitrary similar legal terms."""
    compact = name.replace(' ', '')
    for alias, canonical in _LAW_NAME_ALIASES.items():
        for suffix in ('', ' 시행령', ' 시행규칙'):
            if compact == (alias + suffix).replace(' ', ''):
                return canonical + suffix
    return name


def _embedding_queries(queries: list[str]) -> list[str]:
    """Qwen query-side instruction; document vectors remain untouched."""
    if not config.SEARCH_QUERY_INSTRUCTION_ENABLED or 'qwen3-embedding' not in config.EMBEDDING_MODEL.lower():
        return queries
    task = 'Given a South Korean tax-law question, retrieve the statutory provisions that directly answer it'
    return [f'Instruct: {task}\nQuery: {query}' for query in queries]

# ── 우선순위 테이블 ──────────────────────────────────────────────

_LAW_ARTICLE_PRIORITY: dict[str, int] = {
    "법률":     0,
    "대통령령":  1,
    "총리령":   2,
    "부령":     2,
    "법령해석례": 3,
}
_LAW_ARTICLE_DEFAULT_PRIORITY = 2

_LAW_ARTICLE_SOURCE_TYPE: dict[str, str] = {
    "법률":     "law",
    "대통령령":  "regulation",
    "총리령":   "rule",
    "부령":     "rule",
    "법령해석례": "interpretation",
}
_LAW_ARTICLE_DEFAULT_SOURCE_TYPE = "law"


def _classify_law_type(law_type: str) -> tuple[int, str]:
    """law_type 문자열로 (priority, source_type)을 결정한다.

    "행정안전부령"·"재정경제부령"처럼 소관부처명이 붙은 부령은 _LAW_ARTICLE_PRIORITY의
    "부령"과 정확히 일치하지 않으므로, '부령'으로 끝나는 값을 별도로 처리한다.
    """
    if law_type in _LAW_ARTICLE_PRIORITY:
        return _LAW_ARTICLE_PRIORITY[law_type], _LAW_ARTICLE_SOURCE_TYPE[law_type]
    if law_type.endswith("부령"):
        return _LAW_ARTICLE_PRIORITY["부령"], _LAW_ARTICLE_SOURCE_TYPE["부령"]
    return _LAW_ARTICLE_DEFAULT_PRIORITY, _LAW_ARTICLE_DEFAULT_SOURCE_TYPE

_DOC_CATEGORY_PRIORITY: dict[str, int] = {
    "법령":    3,
    "시행령":  4,
    "시행규칙": 5,
    "집행기준": 6,
    "기타":    7,
}
_DOC_CATEGORY_DEFAULT_PRIORITY = 7

_DOC_CATEGORY_SOURCE_TYPE: dict[str, str] = {
    "법령":    "law",
    "시행령":  "regulation",
    "시행규칙": "rule",
    "집행기준": "practice_pdf",
    "기타":    "user_pdf",
}
_DOC_CATEGORY_DEFAULT_SOURCE_TYPE = "user_pdf"

# ── 검색 SQL ────────────────────────────────────────────────────

_EMBEDDING_COLUMN = "embedding_v2" if EMBEDDING_VERSION == "v2" else "embedding"

_LAW_ARTICLES_SQL = f"""
SELECT
    id, content_hash, effective_date, law_name, law_type, tax_type,
    article_no, article_title, article_text,
    source_url,
    1 - ({_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM law_articles
WHERE is_current = TRUE
  AND {_EMBEDDING_COLUMN} IS NOT NULL
  AND (index_metadata = '{{}}'::jsonb OR index_metadata->>'source_hash' = content_hash)
  AND ($2::text IS NULL OR tax_type = $2)
ORDER BY {_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $3
"""

# 긴 조문의 항(項) 단위 보조 임베딩 검색 — 히트 시 부모 조문 전체를 반환한다.
# 조문 벡터에서 희석되는 특정 항의 내용(예: 제59조의4 ⑨항)도 검색에 걸리게 함.
_LAW_CLAUSES_SQL = f"""
SELECT
    la.id, la.content_hash, la.effective_date, la.law_name, la.law_type, la.tax_type,
    la.article_no, la.article_title, la.article_text,
    la.source_url,
    1 - (c.{_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM law_article_clauses c
JOIN law_articles la ON la.id = c.article_id
WHERE la.is_current = TRUE
  AND c.{_EMBEDDING_COLUMN} IS NOT NULL
  AND (c.index_metadata = '{{}}'::jsonb OR c.index_metadata->>'source_hash' = la.content_hash)
  AND ($2::text IS NULL OR la.tax_type = $2)
ORDER BY c.{_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $3
"""

_DOCUMENTS_SQL = f"""
SELECT
    id, content,
    metadata,
    1 - ({_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM documents
WHERE {_EMBEDDING_COLUMN} IS NOT NULL
  AND user_id = $2::uuid
  AND ($3 = 'ALL' OR metadata->>'law_name' = $3)
ORDER BY {_EMBEDDING_COLUMN}::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $4
"""

# Legal terms are searched independently of embedding similarity. The patterns
# are parameters, and results remain tied to current official source rows.
_KEYWORD_ARTICLES_SQL = """
SELECT id, content_hash, effective_date, law_name, law_type, tax_type,
       article_no, article_title, article_text, source_url,
       0.0 AS similarity_score,
       (SELECT COALESCE(SUM(
           CASE WHEN la.article_title ILIKE pattern THEN 3 ELSE 0 END +
           CASE WHEN la.article_text ILIKE pattern THEN 1 ELSE 0 END
       ), 0) FROM unnest($1::text[]) AS pattern) AS keyword_score
FROM law_articles la
WHERE is_current = TRUE
  AND ($2::text IS NULL OR tax_type = $2)
  AND (article_title ILIKE ANY($1::text[]) OR article_text ILIKE ANY($1::text[]))
ORDER BY keyword_score DESC, article_no
LIMIT $3
"""

_SEARCH_STOPWORDS = {
    "무엇", "어떤", "어떻게", "있는지", "경우", "대해", "설명", "설명하시오", "문제",
    "회사", "회사는", "회사의", "각각", "발생", "발생할", "확인", "판단", "자료",
    "법인세법", "부가가치세법", "소득세법", "국세기본법", "시행령", "시행규칙",
    "것은", "있다", "한다", "해당", "거래", "받았다", "제공", "관련",
}


def issue_keyword_terms(query: str, law_filter: str, limit: int = 6) -> list[str]:
    """Choose bounded Korean legal terms; amounts and company labels are excluded."""
    words = re.findall(r"[가-힣]{2,}|제\d+조(?:의\d+)?", query)
    terms = []
    for word in words:
        term = re.sub(r"(?:에서는|에서|으로|에게|까지|부터|에는|이나|이라|라는|하고|하여|한다|하는|되는|되어|했다|였다|은|는|이|가|을|를|의|에|과|와|도)$", "", word)
        if len(term) < 2 or term in _SEARCH_STOPWORDS or term in law_filter or term in terms:
            continue
        terms.append(term)
    return terms[-limit:]


async def _search_keyword_articles(query: str, law_filter: str, top_k: int) -> list[HybridSearchResult]:
    terms = issue_keyword_terms(query, law_filter)
    if not terms:
        return []
    patterns = [f"%{term}%" for term in terms]
    tax_type_filter = None if law_filter == "ALL" else law_filter
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_KEYWORD_ARTICLES_SQL, patterns, tax_type_filter, top_k)
    return [_row_to_article_result(row) for row in rows]


# ── 내부 검색 함수 ───────────────────────────────────────────────

def _row_to_article_result(r) -> HybridSearchResult:
    law_type = r["law_type"] or ""
    priority, source_type = _classify_law_type(law_type)

    article_header = r["article_no"]
    if r["article_title"]:
        article_header += f" [{r['article_title']}]"

    return HybridSearchResult(
        content=f"{article_header}\n{r['article_text']}",
        source=r["source_url"] or r["law_name"],
        law_name=r["law_name"],
        category=law_type,
        source_type=source_type,
        similarity_score=round(float(r["similarity_score"]), 4),
        priority=priority,
        article_no=r["article_no"],
        origin_kind="official_law",
        source_id=str(r.get("id", r.get("source_id", ""))),
        effective_date=str(r.get("effective_date", "") or ""),
        content_hash=r.get("content_hash", ""),
        original_text=r["article_text"],
    )


async def _search_law_articles(
    q_emb: list[float],
    law_filter: str,
    top_k: int,
) -> list[HybridSearchResult]:
    """law_articles 조문 벡터 + law_article_clauses 항 벡터를 함께 검색한다.

    같은 조문이 양쪽에서 나오면 유사도가 높은 쪽만 남긴다 (항 히트도 컨텍스트는 조문 전체).
    """
    tax_type_filter = None if law_filter == "ALL" else law_filter

    pool = await get_pool()
    async with pool.acquire() as conn:
        article_rows = await conn.fetch(_LAW_ARTICLES_SQL, q_emb, tax_type_filter, top_k)
        clause_rows  = await conn.fetch(_LAW_CLAUSES_SQL, q_emb, tax_type_filter, top_k)

    best: dict[tuple[str, str], HybridSearchResult] = {}
    for r in list(article_rows) + list(clause_rows):
        result = _row_to_article_result(r)
        key = (result.law_name, r["article_no"])
        if key not in best or result.similarity_score > best[key].similarity_score:
            best[key] = result

    results = sorted(best.values(), key=lambda x: -x.similarity_score)[:top_k]
    return results


async def _search_documents(
    q_emb: list[float],
    law_filter: str,
    top_k: int,
    user_id: str,
) -> list[HybridSearchResult]:
    """documents 테이블(PDF 업로드) 벡터 검색. user_id 소유 문서만 반환."""
    if not user_id:
        raise ValueError("documents 검색에는 user_id가 필요합니다.")
    uid = _uuid.UUID(user_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_DOCUMENTS_SQL, q_emb, uid, law_filter, top_k)

    results = []
    for r in rows:
        meta     = r["metadata"] or {}
        category = meta.get("category", "기타")
        law_name = meta.get("law_name", "")
        source   = meta.get("source", "")
        location = ", ".join(
            f"{label} {meta[key]}" for key, label in
            (("page", "페이지"), ("slide", "슬라이드"),
             ("section", "구역"), ("table", "표"), ("row", "행"))
            if meta.get(key) is not None
        )
        if meta.get("ocr"):
            location = f"{location}, OCR 추출" if location else "OCR 추출"

        priority    = _DOC_CATEGORY_PRIORITY.get(category, _DOC_CATEGORY_DEFAULT_PRIORITY)
        source_type = "user_pdf"

        results.append(HybridSearchResult(
            content=r["content"],
            source=source,
            law_name=law_name,
            category=category,
            source_type=source_type,
            similarity_score=round(float(r["similarity_score"]), 4),
            priority=priority,
            document_location=location,
            origin_kind="user_document",
            source_id=str(r.get("id", "")),
            content_hash=digest(r["content"]),
            original_text=r["content"],
        ))

    return results


# ── 멀티쿼리 유틸리티 ─────────────────────────────────────────────

def _rrf_merge(
    results_per_query: list[list[HybridSearchResult]],
    top_k: int,
    k: int = 60,
) -> list[HybridSearchResult]:
    """여러 쿼리 결과를 RRF(Reciprocal Rank Fusion)로 결합. k=60은 표준값."""
    scores: dict[str, float] = {}
    result_map: dict[str, HybridSearchResult] = {}

    for results in results_per_query:
        for rank, r in enumerate(results):
            key = r.content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1) + 0.3 * r.similarity_score
            if key not in result_map:
                result_map[key] = r

    sorted_keys = sorted(scores, key=lambda key: -scores[key])
    return [result_map[key] for key in sorted_keys[:top_k]]


def _fuse_issue_rankings(rankings: list[list[HybridSearchResult]], top_k: int,
                         k: int = 60, weights: list[float] | None = None) -> list[HybridSearchResult]:
    """Fuse vector and keyword lists by server-owned source identity."""
    scores: dict[tuple[str, str], float] = {}
    results: dict[tuple[str, str], HybridSearchResult] = {}
    for index, ranking in enumerate(rankings):
        weight = weights[index] if weights is not None else 1.0
        for rank, result in enumerate(ranking):
            key = (result.law_name, result.article_no)
            scores[key] = scores.get(key, 0.0) + weight / (k + rank + 1)
            if key not in results or result.similarity_score > results[key].similarity_score:
                prior = results[key].retrieval_scores if key in results else {}
                results[key] = replace(result, retrieval_scores={**prior, **result.retrieval_scores})
            else:
                results[key].retrieval_scores.update(result.retrieval_scores)
    keys = sorted(scores, key=lambda key: (-scores[key], results[key].priority,
                                            -results[key].similarity_score, key))
    for key in keys:
        results[key].retrieval_scores['rrf'] = scores[key]
    return [results[key] for key in keys[:top_k]]


def _preserve_dense_leaders(rows, primary):
    """Keep two primary-query official provisions through candidate fusion.

    Admission to the bounded candidate pool is not a relevance approval. It
    prevents multiple low-ranking lexical matches from evicting every leader.
    """
    leaders = [r for r in primary if r.origin_kind == 'official_law'
               and r.article_no and r.source_type != 'interpretation'][:2]
    present = {(r.law_name, r.article_no) for r in rows}
    additions = [r for r in leaders if (r.law_name, r.article_no) not in present]
    return rows + additions, additions


def _longest_common_run(left: str, right: str) -> int:
    """Longest continuous title phrase shared with the user's question."""
    previous = [0] * (len(right) + 1)
    longest = 0
    for char in left:
        current = [0] * (len(right) + 1)
        for index, other in enumerate(right, 1):
            if char == other:
                current[index] = previous[index - 1] + 1
                longest = max(longest, current[index])
        previous = current
    return longest


def _rescue_title_hits(rows: list[HybridSearchResult], candidates: list[HybridSearchResult],
                       original_query: str) -> tuple[list[HybridSearchResult], list[HybridSearchResult]]:
    """Admit at most two clear title matches without evicting fused evidence."""
    question = re.sub(r'[^가-힣A-Za-z0-9]', '', original_query).lower()[:2000]
    present = {(row.law_name, row.article_no) for row in rows}
    ranked = []
    for row in candidates:
        key = (row.law_name, row.article_no)
        if key in present or row.origin_kind != 'official_law' or row.priority != 0 or not row.article_no:
            continue
        header = row.content.split('\n', 1)[0]
        title = header.split('[', 1)[-1].rstrip(']') if '[' in header else ''
        title = re.sub(r'[^가-힣A-Za-z0-9]', '', title).lower()[:120]
        if not title:
            continue
        match = _longest_common_run(question, title)
        if match < 6 or match / len(title) < 0.35:
            continue
        ranked.append((match / len(title), match, row.priority, row.similarity_score, row))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2], -item[3]))
    additions = [item[-1] for item in ranked[:2]]
    return rows + additions, additions


def _retrieval_outputs(output):
    # LangSmith versions can pass the result directly or wrap it as output.
    rows = output.get('output', []) if isinstance(output, dict) else output
    return {'articles': [{'source_id': r.source_id, 'law': r.law_name, 'article': r.article_no,
                          'scores': r.retrieval_scores} for r in rows]}


@traceable(name='issue_hybrid_retrieval', run_type='retriever',
           process_inputs=lambda inputs: {'law_filter': inputs.get('law_filter'),
                                          'query_count': len(inputs.get('queries', []))},
           process_outputs=_retrieval_outputs)
def _names_law(text: str) -> bool:
    """True when the text itself names the statute of its first article reference."""
    references = extract_constraints(text).references if config.SEARCH_REGEX_ENABLED else ()
    reference = references[0] if references and references[0].law_name else extract_law_reference(text)
    return bool(reference and reference.article_no and reference.law_name)


def _direct_in_scope(row, law_filter: str, text: str) -> bool:
    """An article the text names with its statute stays even when the issue's own law differs.

    The issue filter only limits unnamed matches. A rule often depends on another act
    (a penalty in the income tax act applied through the framework act), and an
    official original named by statute and article is exactly what was asked for.
    """
    return (law_filter == "ALL" or row.law_name == law_filter
            or row.law_name.startswith(law_filter + " 시행") or _names_law(text))


async def _search_issue_candidates(queries: list[str], law_filter: str,
                                   original_query: str,
                                   diagnostics: dict | None = None) -> list[HybridSearchResult]:
    """Independent dense and BM25 branches; all results retain source identity."""
    started = time.perf_counter()
    diagnostics = diagnostics if diagnostics is not None else {}
    timings = diagnostics.setdefault('timings_ms', {})
    constraint_query = original_query or queries[0]
    constraints = extract_constraints(constraint_query) if config.SEARCH_REGEX_ENABLED else None
    if constraints:
        diagnostics['regex'] = {'reference_count': len(constraints.references),
                                'date_count': constraints.date_count,
                                'protected_value_count': constraints.amount_count,
                                'lookup_only': constraints.lookup_only}
        if constraints.lookup_only:
            # A literal original request cannot be broadened to another law or
            # article with a similar name/number by lexical/vector/graph search.
            direct_hits = await asyncio.gather(*[
                _lookup_referenced_article(r.canonical, law_filter) for r in constraints.references[:6]])
            hits = list({(r.law_name, r.article_no): r for r in direct_hits if r}.values())
            diagnostics['exact_reference_route'] = True
            diagnostics['final_ids'] = [(r.law_name, r.article_no) for r in hits]
            timings['total'] = round((time.perf_counter() - started) * 1000, 2)
            run = get_current_run_tree()
            if run:
                try:
                    run.add_metadata({'retrieval': diagnostics})
                except Exception:
                    logger.warning('[SEARCH] retrieval diagnostics could not be attached')
            return hits
    if config.SEARCH_FUZZY_ENABLED:
        expanded = [expand_fuzzy_terms(q) for q in queries]
        queries = [q for q, _ in expanded]
        # Only dictionary expansions, never user amounts/source text, in trace.
        diagnostics['fuzzy'] = {'expansion_count': sum(len(terms) for _, terms in expanded),
                                'terms': list(dict.fromkeys(t for _, terms in expanded for t in terms))}
    candidate_k, result_k = TOP_K * 3, TOP_K + 3
    async def dense():
        branch_start = time.perf_counter()
        try:
            embedding_start = time.perf_counter()
            vectors = await cached_embed_queries(_embedding_queries(queries), embedder=embed_texts,
                                                 diagnostics=diagnostics)
            timings['embedding'] = round((time.perf_counter() - embedding_start) * 1000, 2)
            rows = await asyncio.gather(*[
                _search_law_articles(vector, law_filter, candidate_k) for vector in vectors])
            for ranking in rows:
                for row in ranking:
                    row.retrieval_scores['vector'] = row.similarity_score
            return rows
        except Exception as error:
            logger.warning('[SEARCH] vector branch unavailable (%s)', type(error).__name__)
            diagnostics['vector_error'] = type(error).__name__
            return []
        finally:
            timings['dense'] = round((time.perf_counter() - branch_start) * 1000, 2)
    async def keyword(query):
        branch_start = time.perf_counter()
        try:
            if config.SEARCH_LEXICAL_BACKEND == 'bm25':
                try:
                    hits = await search_bm25_articles(query, law_filter, candidate_k, diagnostics)
                    diagnostics['lexical_backend'] = 'bm25'
                    return hits
                except Exception as error:
                    diagnostics['bm25_error'] = type(error).__name__
                    logger.warning('[SEARCH] BM25 unavailable (%s); using indexed keyword search',
                                   type(error).__name__)
            diagnostics['lexical_backend'] = 'trigram'
            return await _search_keyword_articles(query, law_filter, candidate_k)
        except Exception as error:
            logger.warning('[SEARCH] keyword branch unavailable (%s)', type(error).__name__)
            diagnostics.setdefault('keyword_errors', []).append(type(error).__name__)
            return []
        finally:
            timings['lexical'] = round((time.perf_counter() - branch_start) * 1000, 2)
    vector_rankings, keyword_hits = await asyncio.gather(dense(), keyword(queries[0]))
    if diagnostics is not None:
        diagnostics['vector_counts'] = [len(rows) for rows in vector_rankings]
        diagnostics['vector_ids'] = [[(row.law_name, row.article_no) for row in rows]
                                     for rows in vector_rankings]
    rankings = [[row for row in ranking if row.similarity_score >= SIMILARITY_THRESHOLD]
                for ranking in vector_rankings]
    if diagnostics is not None:
        diagnostics['threshold_counts'] = [len(rows) for rows in rankings]
    keyword_rankings = [keyword_hits]
    if diagnostics is not None:
        diagnostics['keyword_ids'] = [[(row.law_name, row.article_no) for row in hits]
                                      for hits in keyword_rankings]
    rankings.extend(keyword_rankings)
    bm25 = diagnostics.get('lexical_backend') == 'bm25'
    fusion_k = config.SEARCH_RRF_K if bm25 else 60
    weights = [1.0] * len(vector_rankings) + [config.SEARCH_LEXICAL_WEIGHT if bm25 else 1.0]
    diagnostics['rrf_k'], diagnostics['rrf_weights'] = fusion_k, weights
    results = _fuse_issue_rankings(rankings, result_k, fusion_k, weights)
    if ISSUE_TITLE_RESCUE:
        pool = list({(row.law_name, row.article_no): row for ranking in [*vector_rankings, *keyword_rankings]
                     for row in ranking}.values())
        results, rescued = _rescue_title_hits(results, pool, original_query or queries[0])
        if diagnostics is not None:
            diagnostics['title_rescue_ids'] = [(row.law_name, row.article_no) for row in rescued]
    if bm25:
        results, rescued = _preserve_dense_leaders(results, rankings[0] if vector_rankings else [])
        diagnostics['dense_rescue_ids'] = [(row.law_name, row.article_no) for row in rescued]
    if diagnostics is not None:
        diagnostics['fused_ids'] = [(row.law_name, row.article_no) for row in results]
    # Refined queries may identify missing articles even when the original
    # question contained no reference. Resolve those against the official DB.
    lookup_queries = [*queries, original_query]
    if config.SEARCH_REGEX_ENABLED:
        lookup_queries += [ref.canonical for text in [*queries, original_query] if text
                           for ref in extract_constraints(text).references[:6]]
    lookup_texts = [text for text in dict.fromkeys(lookup_queries) if text]
    directs = await asyncio.gather(*[_lookup_referenced_article(text, law_filter) for text in lookup_texts])
    direct_rows = [row for text, row in zip(lookup_texts, directs)
                   if row and _direct_in_scope(row, law_filter, text)]
    if direct_rows:
        limit = result_k + (2 if ISSUE_TITLE_RESCUE else 0) + (2 if bm25 else 0)
        results = list({(row.law_name, row.article_no): row for row in [*direct_rows, *results]}.values())[:limit]
    if diagnostics is not None:
        diagnostics['direct_ids'] = [(row.law_name, row.article_no) for row in direct_rows]
    graph_start = time.perf_counter()
    results = await expand_graph(results, original_query or queries[0])
    timings['graph'] = round((time.perf_counter() - graph_start) * 1000, 2)
    if diagnostics is not None:
        diagnostics['graph_ids'] = [(row.law_name, row.article_no) for row in results]
    async def recover(result):
        if result.origin_kind != 'official_law' or not has_missing_items(result.content):
            return result
        replacement = await _lookup_referenced_article(f'{result.law_name} {result.article_no}', result.law_name)
        if replacement and not has_missing_items(replacement.content):
            replacement.similarity_score = result.similarity_score
            replacement.graph_evidence = result.graph_evidence
            replacement.retrieval_scores = dict(result.retrieval_scores)
            return replacement
        return result
    final = list(await asyncio.gather(*(recover(result) for result in results)))
    if config.SEARCH_MMR_ENABLED and len(final) >= 3:
        mmr_start = time.perf_counter()
        pins = {(r.law_name, r.article_no) for r in direct_rows}
        pins.update((r.law_name, r.article_no) for r in final if r.graph_evidence)
        pins.update(map(tuple, diagnostics.get('title_rescue_ids', [])))
        pins.update(map(tuple, diagnostics.get('dense_rescue_ids', [])))
        try:
            vectors = await _candidate_vectors(final)
            final = mmr_order(final, vectors, pinned=pins, lambda_mult=config.SEARCH_MMR_LAMBDA)
            diagnostics['mmr'] = {'lambda': config.SEARCH_MMR_LAMBDA, 'vector_count': len(vectors),
                                  'pinned_count': len(pins), 'preserves_candidates': True}
        except Exception as error:
            diagnostics['mmr_error'] = type(error).__name__
            logger.warning('[SEARCH] MMR unavailable (%s); candidate order retained', type(error).__name__)
        timings['mmr'] = round((time.perf_counter() - mmr_start) * 1000, 2)
    if diagnostics is not None:
        diagnostics['final_ids'] = [(row.law_name, row.article_no) for row in final]
    timings['total'] = round((time.perf_counter() - started) * 1000, 2)
    run = get_current_run_tree()
    if run:
        try:
            run.add_metadata({'retrieval': diagnostics})
        except Exception:
            logger.warning('[SEARCH] retrieval diagnostics could not be attached')
    return final


async def _candidate_vectors(results):
    """Use only vectors tied to these exact official source rows and hashes."""
    expected = {int(r.source_id): r for r in results
                if r.origin_kind == 'official_law' and r.source_id.isdigit()}
    if not expected:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f'''SELECT id, content_hash, {_EMBEDDING_COLUMN} AS vector
            FROM law_articles WHERE is_current=TRUE AND id=ANY($1::bigint[])
              AND (index_metadata='{{}}'::jsonb OR index_metadata->>'source_hash'=content_hash)''', list(expected))
    return {str(r['id']): r['vector'] for r in rows if r['vector'] is not None
            and r['content_hash'] == expected[r['id']].content_hash}


async def _search_all(
    q_emb: list[float],
    law_filter: str,
    fetch_k: int,
    user_id: str,
) -> list[HybridSearchResult]:
    """한 임베딩으로 law_articles + documents 검색 후 임계값 필터링, 우선순위 정렬."""
    law_results, doc_results = await asyncio.gather(
        _search_law_articles(q_emb, law_filter, fetch_k),
        _search_documents(q_emb, law_filter, fetch_k, user_id),
    )
    merged = law_results + doc_results
    merged = [r for r in merged if r.similarity_score >= SIMILARITY_THRESHOLD]
    merged.sort(key=lambda r: (r.priority, -r.similarity_score))
    return merged


# ── 공개 함수 ────────────────────────────────────────────────────

def format_hybrid_context(results: list[HybridSearchResult]) -> str:
    """하이브리드 검색 결과를 LLM 컨텍스트 문자열로 포맷한다."""
    return context_from_records(record_from_result(r) for r in results)


async def _lookup_referenced_article(
    query: str, law_filter: str,
) -> HybridSearchResult | None:
    """질문이 조문번호를 직접 언급하면 벡터 검색을 거치지 않고 해당 조문을 조회한다.

    조문번호("제39조")는 임베딩 유사도에 거의 반영되지 않아 벡터 검색만으로는
    직접 질의를 안정적으로 찾지 못한다 (평가셋 direct-02로 확인된 약점).
    법령명은 질문에서 우선 추출하고, 없으면 세목 필터(law_filter)를 사용한다.
    """
    references = extract_constraints(query).references if config.SEARCH_REGEX_ENABLED else ()
    reference = (references[0] if references and references[0].law_name else extract_law_reference(query))
    if not reference or not reference.article_no:
        return None
    law_name = reference.law_name or (law_filter if law_filter != "ALL" else None)
    if not law_name:
        return None
    law_name = _canonical_lookup_law(law_name)

    article_no = reference.article_no
    article = await get_law_article(law_name, article_no)
    if not article:
        return None

    priority, source_type = _classify_law_type(article.law_type)
    header = article.article_no + (f" [{article.article_title}]" if article.article_title else "")
    return HybridSearchResult(
        content=f"{header}\n{article.article_text}",
        source=article.source_url or article.law_name,
        law_name=article.law_name,
        category=article.law_type,
        source_type=source_type,
        similarity_score=1.0,   # 직접 조회 — 항상 최상위
        priority=priority,
        article_no=article.article_no,
        origin_kind="official_law",
        source_id=getattr(article, "source_id", ""),
        effective_date=article.effective_date,
        content_hash=getattr(article, "content_hash", ""),
        original_text=article.article_text,
    )


def _prepend_direct_hit(
    direct: HybridSearchResult | None,
    results: list[HybridSearchResult],
) -> list[HybridSearchResult]:
    """직접 조회된 조문을 결과 맨 앞에 두고 중복을 제거한다."""
    if direct is None:
        return results
    deduped = [
        r for r in results
        if not (r.law_name == direct.law_name and r.content.split("\n", 1)[0] == direct.content.split("\n", 1)[0])
    ]
    return [direct] + deduped[: TOP_K - 1]


async def hybrid_search(
    queries: list[str],
    law_filter: str = "ALL",
    user_id: str = "",
    original_query: str = "",
    official_only: bool = False,
    issue_mode: bool = False,
    diagnostics: dict | None = None,
) -> list[HybridSearchResult]:
    """law_articles + documents를 동시에 검색하고 우선순위 순으로 병합한다.

    질문이 조문번호를 직접 언급하면 해당 조문을 벡터 검색 없이 조회해 최상위에 둔다.
    단일 쿼리는 직접 벡터 검색, 복수 쿼리는 RRF로 결합한다.
    """
    if not queries:
        return []

    if official_only and issue_mode:
        return await _search_issue_candidates(queries, law_filter, original_query, diagnostics)

    t0 = time.perf_counter()

    async def candidates(vector, count):
        if not official_only:
            return await _search_all(vector, law_filter, count, user_id)
        rows = await _search_law_articles(vector, law_filter, count)
        return sorted([r for r in rows if r.similarity_score >= SIMILARITY_THRESHOLD],
                      key=lambda r: (r.priority, -r.similarity_score))

    direct = await _lookup_referenced_article(original_query or queries[0], law_filter)
    if direct:
        logger.info("[SEARCH] 조문번호 직접 질의 감지 — %s %s 최상위 배치",
                    direct.law_name, direct.content.split(chr(10), 1)[0])

    if len(queries) == 1:
        q_emb = (await embed_texts(queries))[0]
        merged = await candidates(q_emb, TOP_K)
        candidates = merged[:TOP_K]
        final = candidates
        final  = _prepend_direct_hit(direct, final)
        if not final:
            logger.warning(
                "[SEARCH] 검색 결과 없음 (필터=%s) — law_articles 또는 documents에 임베딩된 데이터가 없습니다.",
                law_filter,
            )
        else:
            logger.info(
                "[SEARCH] 필터=%s | 후보 %d건 → 최종 %d건 (%.2fs)",
                law_filter, len(candidates), len(final), time.perf_counter() - t0,
            )
        return await expand_graph(final, original_query or queries[0])

    fetch_k = TOP_K * 2
    q_embs = await embed_texts(queries)
    results_per_query = await asyncio.gather(*[
        candidates(q_emb, fetch_k)
        for q_emb in q_embs
    ])

    merged = _rrf_merge(list(results_per_query), top_k=TOP_K)
    final = merged[:TOP_K]
    final  = _prepend_direct_hit(direct, final)

    logger.info(
        "[MULTI-QUERY] %d개 쿼리 → RRF %d건 → 최종 %d건 (%.2fs)",
        len(queries), len(merged), len(final), time.perf_counter() - t0,
    )
    return await expand_graph(final, original_query or queries[0])

async def search_user_documents(query: str, user_id: str, top_k: int = 3) -> list[HybridSearchResult]:
    """사용자 PDF만 조회한다. 인증 사용자 ID는 서버가 전달한다."""
    _uuid.UUID(user_id)
    if not query.strip() or not 1 <= top_k <= 5:
        raise ValueError("Invalid document search parameters")
    vector = (await embed_texts([query]))[0]
    results = await _search_documents(vector, "ALL", top_k, user_id)
    return [r for r in results if r.similarity_score >= SIMILARITY_THRESHOLD]

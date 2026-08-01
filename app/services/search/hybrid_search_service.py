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

from app.database import get_pool
from app.schemas.law import (
    HybridSearchResult,
    LawArticleDetail,
    LawReferenceTarget,
    ParsedLawReference,
)
from app.services.embedding_service import embed_texts, get_http_client
from app.services.law.reference_parser import (
    InvalidLawReference,
    LawReference,
    extract_law_reference,
    normalize_article_no,
    parse_law_reference,
)
from app.services.law.structure_parser import resolve_reference_target
from config import OLLAMA_BASE_URL, RERANK_MODEL, SIMILARITY_THRESHOLD, TOP_K

logger = logging.getLogger(__name__)

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

# ── 리랭킹 설정 ─────────────────────────────────────────────────
_RERANK_URL           = f"{OLLAMA_BASE_URL}/api/rerank"
_RERANK_CONTENT_LIMIT = 500

# ── 검색 SQL ────────────────────────────────────────────────────

_LAW_ARTICLES_SQL = """
SELECT
    law_name, law_type, tax_type,
    article_no, article_title, article_text,
    source_url,
    1 - (embedding::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM law_articles
WHERE is_current = TRUE
  AND embedding IS NOT NULL
  AND ($2::text IS NULL OR tax_type = $2)
ORDER BY embedding::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $3
"""

# 긴 조문의 항(項) 단위 보조 임베딩 검색 — 히트 시 부모 조문 전체를 반환한다.
# 조문 벡터에서 희석되는 특정 항의 내용(예: 제59조의4 ⑨항)도 검색에 걸리게 함.
_LAW_CLAUSES_SQL = """
SELECT
    la.law_name, la.law_type, la.tax_type,
    la.article_no, la.article_title, la.article_text,
    la.source_url,
    1 - (c.embedding::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM law_article_clauses c
JOIN law_articles la ON la.id = c.article_id
WHERE la.is_current = TRUE
  AND c.embedding IS NOT NULL
  AND ($2::text IS NULL OR la.tax_type = $2)
ORDER BY c.embedding::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $3
"""

_DOCUMENTS_SQL = """
SELECT
    content,
    metadata,
    1 - (embedding::halfvec(2560) <=> $1::vector::halfvec(2560)) AS similarity_score
FROM documents
WHERE embedding IS NOT NULL
  AND user_id = $2::uuid
  AND ($3 = 'ALL' OR metadata->>'law_name' = $3)
ORDER BY embedding::halfvec(2560) <=> $1::vector::halfvec(2560)
LIMIT $4
"""


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

        priority    = _DOC_CATEGORY_PRIORITY.get(category, _DOC_CATEGORY_DEFAULT_PRIORITY)
        source_type = _DOC_CATEGORY_SOURCE_TYPE.get(category, _DOC_CATEGORY_DEFAULT_SOURCE_TYPE)

        results.append(HybridSearchResult(
            content=r["content"],
            source=source,
            law_name=law_name,
            category=category,
            source_type=source_type,
            similarity_score=round(float(r["similarity_score"]), 4),
            priority=priority,
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


# ── 리랭킹 ───────────────────────────────────────────────────────

async def _rerank(
    original_query: str,
    results: list[HybridSearchResult],
    top_k: int,
) -> list[HybridSearchResult]:
    """Ollama /api/rerank로 결과를 재정렬한다. 미설정 또는 실패 시 원본 top_k 슬라이싱."""
    if not RERANK_MODEL or not results:
        return results[:top_k]

    documents = [r.content[:_RERANK_CONTENT_LIMIT] for r in results]
    t0 = time.perf_counter()
    try:
        client = get_http_client()
        resp = await client.post(
            _RERANK_URL,
            json={
                "model":     RERANK_MODEL,
                "query":     original_query,
                "documents": documents,
            },
        )
        resp.raise_for_status()
        ranked = resp.json().get("results", [])
        reranked = [results[item["index"]] for item in ranked[:top_k]]
        logger.info("[RERANK] %d→%d건 재정렬 완료 (%.2fs)", len(results), len(reranked), time.perf_counter() - t0)
        return reranked
    except Exception as e:
        logger.warning("[RERANK] 실패 — 기존 정렬 사용: %s", e)
        return results[:top_k]


# ── 조문 원문 조회 ───────────────────────────────────────────────

_ARTICLE_LOOKUP_SQL = """
SELECT law_name, law_type, tax_type, article_no, article_title, article_text,
       effective_date, amendment_date, source_url
FROM law_articles
WHERE is_current = TRUE
  AND regexp_replace(law_name, '\\s+', '', 'g') = regexp_replace($1, '\\s+', '', 'g')
  AND article_no = $2
-- 국가법령정보 API는 절/관 구조 표제(예: "제4절 세액의 계산")를 다음 조문과
-- 같은 조문번호를 가진 별도 행으로 내려주는 경우가 있어(파서 한계),
-- 실제 조문 본문("제55조(세율)..."로 시작)을 우선 채택한다.
ORDER BY (article_text LIKE $2 || '%') DESC, length(article_text) DESC, updated_at DESC
LIMIT 1
"""


async def get_law_article(law_name: str, article_no: str) -> LawArticleDetail | None:
    """법령명 + 조문번호로 조문 원문을 조회한다 (공백 표기 차이 무시).

    조문 원문 뷰어(채팅 답변의 인용을 클릭했을 때) 및 인용 검증에 사용.
    """
    law_name = law_name.strip()
    try:
        parsed_reference = parse_law_reference(article_no)
    except InvalidLawReference:
        normalized_article_no = normalize_article_no(article_no)
        try:
            parsed_reference = parse_law_reference(normalized_article_no)
        except InvalidLawReference:
            parsed_reference = None
    article_no = normalize_article_no(article_no)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_ARTICLE_LOOKUP_SQL, law_name, article_no)
    if not row:
        return None
    reference = None
    target = None
    if parsed_reference and parsed_reference.article is not None:
        canonical_reference = LawReference(
            law_name=row["law_name"],
            article=parsed_reference.article,
            article_branch=parsed_reference.article_branch,
            paragraph=parsed_reference.paragraph,
            item=parsed_reference.item,
            item_branch=parsed_reference.item_branch,
            subitem=parsed_reference.subitem,
        )
        reference = ParsedLawReference(
            law_name=row["law_name"],
            article=canonical_reference.article,
            article_branch=canonical_reference.article_branch,
            paragraph=canonical_reference.paragraph,
            item=canonical_reference.item,
            item_branch=canonical_reference.item_branch,
            subitem=canonical_reference.subitem,
            canonical=canonical_reference.canonical,
        )
        resolved = resolve_reference_target(row["article_text"], canonical_reference)
        if resolved is not None:
            target = LawReferenceTarget(
                exists=resolved.exists,
                level=resolved.level,
                paragraph=resolved.paragraph,
                item=resolved.item,
                item_branch=resolved.item_branch,
                subitem=resolved.subitem,
                text=resolved.text,
                detail=resolved.detail,
            )

    return LawArticleDetail(
        law_name=row["law_name"],
        law_type=row["law_type"],
        tax_type=row["tax_type"],
        article_no=row["article_no"],
        article_title=row["article_title"],
        article_text=row["article_text"],
        effective_date=row["effective_date"],
        amendment_date=row["amendment_date"],
        source_url=row["source_url"] or "",
        reference=reference,
        target=target,
    )


# ── 공개 함수 ────────────────────────────────────────────────────

def format_hybrid_context(results: list[HybridSearchResult]) -> str:
    """하이브리드 검색 결과를 LLM 컨텍스트 문자열로 포맷한다."""
    if not results:
        return "관련 문서를 찾지 못했습니다."

    return "\n\n---\n\n".join(
        f"[출처: {r.source} | {r.law_name} | 📌 {r.category} ({r.source_type})]\n"
        f"{r.content}"
        for r in results
    )


async def fetch_hybrid_context(
    query: str,
    law_filter: str = "ALL",
    user_id: str = "",
    original_query: str = "",
) -> str:
    """단일 쿼리 하이브리드 검색 진입점."""
    results = await hybrid_search([query], law_filter=law_filter, user_id=user_id, original_query=original_query)
    return format_hybrid_context(results)


async def _lookup_referenced_article(
    query: str, law_filter: str,
) -> HybridSearchResult | None:
    """질문이 조문번호를 직접 언급하면 벡터 검색을 거치지 않고 해당 조문을 조회한다.

    조문번호("제39조")는 임베딩 유사도에 거의 반영되지 않아 벡터 검색만으로는
    직접 질의를 안정적으로 찾지 못한다 (평가셋 direct-02로 확인된 약점).
    법령명은 질문에서 우선 추출하고, 없으면 세목 필터(law_filter)를 사용한다.
    """
    reference = extract_law_reference(query)
    if not reference or not reference.article_no:
        return None
    law_name = reference.law_name or (law_filter if law_filter != "ALL" else None)
    if not law_name:
        return None

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
) -> list[HybridSearchResult]:
    """law_articles + documents를 동시에 검색하고 우선순위 순으로 병합한다.

    질문이 조문번호를 직접 언급하면 해당 조문을 벡터 검색 없이 조회해 최상위에 둔다.
    단일 쿼리는 직접 벡터 검색, 복수 쿼리는 RRF로 결합 후 리랭킹.
    """
    if not queries:
        return []

    t0 = time.perf_counter()

    direct = await _lookup_referenced_article(original_query or queries[0], law_filter)
    if direct:
        logger.info("[SEARCH] 조문번호 직접 질의 감지 — %s %s 최상위 배치",
                    direct.law_name, direct.content.split(chr(10), 1)[0])

    if len(queries) == 1:
        q_emb = (await embed_texts(queries))[0]
        fetch_k = TOP_K * 3 if RERANK_MODEL else TOP_K
        merged = await _search_all(q_emb, law_filter, fetch_k, user_id)
        final  = await _rerank(original_query or queries[0], merged, TOP_K)
        final  = _prepend_direct_hit(direct, final)
        if not final:
            logger.warning(
                "[SEARCH] 검색 결과 없음 (필터=%s) — law_articles 또는 documents에 임베딩된 데이터가 없습니다.",
                law_filter,
            )
        else:
            logger.info(
                "[SEARCH] 필터=%s | 후보 %d건 → 최종 %d건 (%.2fs)",
                law_filter, len(merged), len(final), time.perf_counter() - t0,
            )
        return final

    fetch_k = TOP_K * 2
    q_embs = await embed_texts(queries)
    results_per_query = await asyncio.gather(*[
        _search_all(q_emb, law_filter, fetch_k, user_id)
        for q_emb in q_embs
    ])

    merged = _rrf_merge(list(results_per_query), top_k=TOP_K * 2)
    final  = await _rerank(original_query or queries[0], merged, TOP_K)
    final  = _prepend_direct_hit(direct, final)

    logger.info(
        "[MULTI-QUERY] %d개 쿼리 → RRF %d건 → 최종 %d건 (%.2fs)",
        len(queries), len(merged), len(final), time.perf_counter() - t0,
    )
    return final

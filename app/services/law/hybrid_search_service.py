"""
services/hybrid_search_service.py — 하이브리드 RAG 검색 (Phase 7)

law_articles(공식 법령 조문)와 documents(PDF 업로드) 두 테이블을
동시에 벡터 검색하고 우선순위에 따라 병합하여 LLM 컨텍스트를 생성한다.

우선순위 (낮을수록 높은 우선순위):
  0 — 법률         (law_articles, law_type=법률)
  1 — 시행령        (law_articles, law_type=대통령령)
  2 — 시행규칙      (law_articles, law_type=총리령/부령)
  3 — 법령 PDF      (documents, category=법령)
  4 — 시행령 PDF    (documents, category=시행령)
  5 — 시행규칙 PDF  (documents, category=시행규칙)
  6 — 집행기준      (documents, category=집행기준)
  7 — 기타 PDF      (documents, category=기타)

공개 법령(law_articles)은 모든 사용자에게 검색 가능.
사용자 업로드 PDF(documents)는 현재 전체 공개 (TODO: uploader 기반 필터링).
"""
import math
from dataclasses import dataclass

from app.database import get_pool
from app.utils.embeddings import embed_texts
from config import TOP_K

# ── 우선순위 테이블 ──────────────────────────────────────────────

_LAW_ARTICLE_PRIORITY: dict[str, int] = {
    "법률":    0,
    "대통령령": 1,
    "총리령":  2,
    "부령":    2,
}
_LAW_ARTICLE_DEFAULT_PRIORITY = 2

_LAW_ARTICLE_SOURCE_TYPE: dict[str, str] = {
    "법률":    "law",
    "대통령령": "regulation",
    "총리령":  "rule",
    "부령":    "rule",
}
_LAW_ARTICLE_DEFAULT_SOURCE_TYPE = "law"

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

# law_articles 검색 — is_current=TRUE, embedding 있는 것만
_LAW_ARTICLES_SQL = """
SELECT
    law_name, law_type, tax_type,
    article_no, article_title, article_text,
    source_url,
    1 - (embedding <=> $1::vector) AS similarity_score
FROM law_articles
WHERE is_current = TRUE
  AND embedding IS NOT NULL
  AND ($2::text IS NULL OR tax_type = $2)
ORDER BY embedding <=> $1::vector
LIMIT $3
"""

# documents 검색 — 기존 match_documents()와 동일한 방식
_DOCUMENTS_SQL = """
SELECT
    content,
    metadata,
    1 - (embedding <=> $1::vector) AS similarity_score
FROM documents
WHERE embedding IS NOT NULL
  AND ($2 = 'ALL' OR metadata->>'law_name' = $2)
ORDER BY embedding <=> $1::vector
LIMIT $3
"""


# ── 결과 타입 ────────────────────────────────────────────────────

@dataclass
class HybridSearchResult:
    """하이브리드 검색 결과 단건."""
    content:          str    # LLM에 전달할 본문
    source:           str    # 출처명 (파일명 또는 법령명)
    law_name:         str
    category:         str    # 법령 위계 레이블
    source_type:      str    # law / regulation / rule / practice_pdf / user_pdf
    similarity_score: float
    priority:         int    # 정렬 기준 (낮을수록 우선)


# ── 내부 검색 함수 ───────────────────────────────────────────────

async def _search_law_articles(
    q_emb: list[float],
    law_filter: str,
    top_k: int,
) -> list[HybridSearchResult]:
    """law_articles 테이블 벡터 검색."""
    tax_type_filter = None if law_filter == "ALL" else law_filter

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LAW_ARTICLES_SQL, q_emb, tax_type_filter, top_k)

    results = []
    for r in rows:
        law_type = r["law_type"] or ""
        priority    = _LAW_ARTICLE_PRIORITY.get(law_type, _LAW_ARTICLE_DEFAULT_PRIORITY)
        source_type = _LAW_ARTICLE_SOURCE_TYPE.get(law_type, _LAW_ARTICLE_DEFAULT_SOURCE_TYPE)

        article_header = r["article_no"]
        if r["article_title"]:
            article_header += f" [{r['article_title']}]"

        results.append(HybridSearchResult(
            content=f"{article_header}\n{r['article_text']}",
            source=r["source_url"] or r["law_name"],
            law_name=r["law_name"],
            category=law_type,
            source_type=source_type,
            similarity_score=round(float(r["similarity_score"]), 4),
            priority=priority,
        ))

    return results


async def _search_documents(
    q_emb: list[float],
    law_filter: str,
    top_k: int,
) -> list[HybridSearchResult]:
    """documents 테이블(PDF 업로드) 벡터 검색."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_DOCUMENTS_SQL, q_emb, law_filter, top_k)

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


# ── 공개 함수 ────────────────────────────────────────────────────

async def hybrid_search(
    query: str,
    law_filter: str = "ALL",
    top_k: int = TOP_K,
) -> list[HybridSearchResult]:
    """
    law_articles + documents를 동시에 검색하고 우선순위 순으로 병합한다.

    Args:
        query:      사용자 질문
        law_filter: 세목 필터 (예: "소득세법"). "ALL"이면 전체 검색.
        top_k:      최종 반환 결과 수

    Returns:
        HybridSearchResult 리스트.
        priority 오름차순 → similarity_score 내림차순 정렬.
        두 테이블 모두 비어있으면 빈 리스트.
    """
    # 임베딩 1회 생성 — 두 테이블에서 공유
    q_emb = (await embed_texts([query]))[0]

    # 각 테이블에서 top_k씩 검색 (병합 전 여유분 확보)
    law_results, doc_results = await _search_law_articles(
        q_emb, law_filter, top_k
    ), await _search_documents(q_emb, law_filter, top_k)

    merged = law_results + doc_results

    # 우선순위 오름차순, 동순위는 유사도 내림차순
    merged.sort(key=lambda r: (r.priority, -r.similarity_score))

    return merged[:top_k]


def format_hybrid_context(results: list[HybridSearchResult]) -> str:
    """
    하이브리드 검색 결과를 LLM 컨텍스트 문자열로 포맷한다.
    기존 _fetch_context() 출력 형식과 동일한 구조를 유지한다.
    """
    if not results:
        return "관련 문서를 찾지 못했습니다."

    return "\n\n---\n\n".join(
        f"[출처: {r.source} | {r.law_name} | 📌 {r.category} ({r.source_type})]\n"
        f"{r.content}"
        for r in results
    )


async def fetch_hybrid_context(query: str, law_filter: str = "ALL") -> str:
    """
    chat_service._fetch_context()의 하이브리드 대체 함수.
    동일한 시그니처로 교체 가능하도록 문자열을 반환한다.
    """
    results = await hybrid_search(query, law_filter=law_filter)
    return format_hybrid_context(results)

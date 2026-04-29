"""
services/law_search_service.py — law_articles 벡터 유사도 검색 (Phase 6)

사용자 질문을 임베딩하여 law_articles 테이블에서 유사한 조문을 검색한다.
기존 PDF RAG(documents 테이블)와는 독립적으로 동작한다.

주요 함수:
  search_law_articles(query, tax_type, top_k) → list[LawSearchResult]
"""
from dataclasses import dataclass

from app.database import get_pool
from app.utils.embeddings import embed_texts
from config import TOP_K


@dataclass
class LawSearchResult:
    """법령 조문 검색 결과 단건."""
    law_name:        str
    law_type:        str
    tax_type:        str
    article_no:      str
    article_title:   str
    article_text:    str
    similarity_score: float   # 코사인 유사도 (0~1, 높을수록 관련성 높음)
    source_url:      str


# ── SQL ────────────────────────────────────────────────────────
# match_documents()와 동일한 코사인 유사도 방식 사용 (vector_cosine_ops / <=>)
# similarity = 1 - cosine_distance
_SEARCH_SQL = """
SELECT
    law_name,
    law_type,
    tax_type,
    article_no,
    article_title,
    article_text,
    source_url,
    1 - (embedding <=> $1::vector) AS similarity_score
FROM law_articles
WHERE is_current = TRUE
  AND embedding IS NOT NULL
  AND ($2::text IS NULL OR tax_type = $2)
ORDER BY embedding <=> $1::vector
LIMIT $3
"""


async def search_law_articles(
    query: str,
    tax_type: str | None = None,
    top_k: int = TOP_K,
) -> list[LawSearchResult]:
    """
    사용자 질문과 유사한 법령 조문을 law_articles 테이블에서 검색한다.

    Args:
        query:    사용자 질문 (예: "프리랜서 노트북 비용처리 돼?")
        tax_type: 세목 필터 (예: "소득세법"). None이면 전체 세목 검색.
        top_k:    반환할 최대 결과 수 (기본값: config.TOP_K)

    Returns:
        LawSearchResult 리스트. similarity_score 내림차순 정렬.
        결과 없으면 빈 리스트.

    Notes:
        - embedding IS NULL인 조문은 검색 대상에서 제외된다.
        - is_current = FALSE(구버전 조문)는 검색 대상에서 제외된다.
    """
    q_emb = (await embed_texts([query]))[0]

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SEARCH_SQL, q_emb, tax_type, top_k)

    return [
        LawSearchResult(
            law_name=r["law_name"],
            law_type=r["law_type"],
            tax_type=r["tax_type"],
            article_no=r["article_no"],
            article_title=r["article_title"],
            article_text=r["article_text"],
            similarity_score=round(float(r["similarity_score"]), 4),
            source_url=r["source_url"],
        )
        for r in rows
    ]


def format_search_results(results: list[LawSearchResult]) -> str:
    """
    검색 결과를 RAG 컨텍스트 문자열로 포맷한다.
    chat_service._fetch_context()의 출력 형식과 동일하게 맞춘다.
    """
    if not results:
        return "관련 법령 조문을 찾지 못했습니다."

    return "\n\n---\n\n".join(
        f"[출처: {r.source_url or r.law_name} | "
        f"{r.law_name} | "
        f"📌 {r.law_type}]\n"
        f"{r.article_no}"
        f"{' [' + r.article_title + ']' if r.article_title else ''}\n"
        f"{r.article_text}"
        for r in results
    )

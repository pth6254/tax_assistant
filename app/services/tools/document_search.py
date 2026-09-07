from app.schemas.tool_call import DocumentSearchRequest
from app.services.search.hybrid_search_service import search_user_documents


async def search(request: DocumentSearchRequest, user_id: str) -> tuple[str, str]:
    results = await search_user_documents(request.query, user_id, request.top_k)
    if not results:
        return "not_found", "현재 사용자 소유 문서에서 관련 내용을 찾지 못했습니다."
    # 현재 검색 결과에는 페이지 정보가 없으므로 페이지 번호를 생성하지 않는다.
    context = "\n\n".join(
        f"[사용자 문서: {r.source}]\n{r.content[:3000]}"
        + ("\n[일부 발췌]" if len(r.content) > 3000 else "")
        for r in results
    )
    return "ok", context

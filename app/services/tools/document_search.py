from app.schemas.tool_call import DocumentSearchRequest
from app.services.search.hybrid_search_service import search_user_documents
from app.services.evidence import context_from_records, record_from_result


async def search(request: DocumentSearchRequest, user_id: str) -> tuple[str, str]:
    results = await search_user_documents(request.query, user_id, request.top_k)
    if not results:
        return "not_found", "현재 사용자 소유 문서에서 관련 내용을 찾지 못했습니다."
    context = context_from_records(record_from_result(r) for r in results)
    return "ok", context

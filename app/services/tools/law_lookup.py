from app.schemas.tool_call import LawLookupRequest
from app.services.law.lookup_service import get_law_article
from app.schemas.law import HybridSearchResult
from app.services.evidence import context_from_records, record_from_result


async def lookup(request: LawLookupRequest) -> tuple[str, str]:
    article = await get_law_article(request.law_name, request.article_no)
    if article is None:
        return "not_found", "요청한 법령 조문을 저장된 자료에서 찾지 못했습니다. 원문을 추측하지 마세요."
    if article.target is not None and not article.target.exists:
        return "not_found", "조문은 있으나 요청한 항·호·목을 본문에서 확인하지 못했습니다. 존재한다고 단정하지 마세요."
    text = article.target.text if article.target and article.target.text else article.article_text
    reference = article.reference.canonical if article.reference else article.article_no
    result = HybridSearchResult(
        content=f"{reference}\n{text}", source=article.source_url,
        law_name=article.law_name, category=article.law_type, source_type="law",
        similarity_score=1, priority=0, article_no=getattr(article, "article_no", request.article_no),
        origin_kind="official_law", source_id=getattr(article, "source_id", ""),
        effective_date=article.effective_date, content_hash=getattr(article, "content_hash", ""),
        original_text=article.article_text,
    )
    return "ok", context_from_records([record_from_result(result)])

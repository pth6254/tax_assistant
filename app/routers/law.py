"""
routers/law.py — 법령 조문 조회 엔드포인트
GET /api/law-articles/lookup?law_name=...&article_no=...  조문 원문 뷰어용
"""
from fastapi import APIRouter, Depends, HTTPException

from app.schemas.law import LawArticleDetail
from app.services.search.hybrid_search_service import get_law_article
from app.core.security import verify_token

router = APIRouter(prefix="/api/law-articles", tags=["law"])


@router.get("/lookup", response_model=LawArticleDetail)
async def lookup_article(
    law_name: str,
    article_no: str,
    user: dict = Depends(verify_token),
):
    article = await get_law_article(law_name, article_no)
    if not article:
        raise HTTPException(status_code=404, detail="해당 조문을 찾을 수 없습니다.")
    return article

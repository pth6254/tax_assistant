"""
routers/chat.py — 채팅 엔드포인트
POST /api/chat
GET  /api/health
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_pool
from app.services import chat_service
from app.utils.jwt import verify_token

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    query:  str
    userId: str = ""
    name:   str = "사용자"


@router.get("/health")
async def health():
    pool = await get_pool()
    async with pool.acquire() as conn:
        ver = await conn.fetchval("SELECT version()")
    return {"status": "ok", "db": ver[:60]}


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: dict = Depends(verify_token),
):
    answer = await chat_service.process_chat(
        query=body.query,
        user_id=user["id"],
    )
    return {"output": answer}

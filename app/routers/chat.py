"""
routers/chat.py — 채팅 엔드포인트
POST /api/chat         비스트리밍 응답
POST /api/chat/stream  SSE 스트리밍 응답
GET  /api/health
"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.database import get_pool
from app.schemas.chat import ChatRequest
from app.services import chat_service
from app.utils.jwt import verify_token

router = APIRouter(prefix="/api", tags=["chat"])


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
    answer, calculator = await chat_service.process_chat(
        query=body.query,
        conversation_id=body.conversation_id,
        user_id=user["id"],
    )
    return {"output": answer, "calculator": calculator}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(verify_token),
):
    """SSE 스트리밍 응답. {"type": "chunk"|"calc", ...} 이벤트를 전송한다."""
    async def generate():
        async for event in chat_service.stream_chat_response(
            query=body.query,
            conversation_id=body.conversation_id,
            user_id=user["id"],
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

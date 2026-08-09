"""
routers/chat.py — 채팅 엔드포인트
POST /api/chat         비스트리밍 응답
POST /api/chat/stream  SSE 스트리밍 응답
"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.database import get_pool
from app.schemas.chat import ChatRequest
from app.services import chat_service
from app.services.conversation_service import require_conversation_owner
from app.core.security import verify_token

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: dict = Depends(verify_token),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conversation_id = await require_conversation_owner(
            conn, body.conversation_id, user["id"],
        )

    answer, calculator = await chat_service.process_chat(
        query=body.query,
        conversation_id=str(conversation_id),
        user_id=user["id"],
    )
    return {"output": answer, "calculator": calculator}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(verify_token),
):
    """SSE 스트리밍 응답. {"type": "chunk"|"calc", ...} 이벤트를 전송한다."""
    # StreamingResponse가 헤더를 전송하기 전에 소유권을 확인해야 오류를
    # 정상적인 HTTP 404로 반환할 수 있다.
    pool = await get_pool()
    async with pool.acquire() as conn:
        conversation_id = await require_conversation_owner(
            conn, body.conversation_id, user["id"],
        )

    async def generate():
        async for event in chat_service.stream_chat_response(
            query=body.query,
            conversation_id=str(conversation_id),
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

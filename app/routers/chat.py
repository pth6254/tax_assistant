"""
routers/chat.py — 채팅 엔드포인트
POST /api/chat         비스트리밍 응답
POST /api/chat/stream  SSE 스트리밍 응답
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.database import get_pool
from app.schemas.chat import ChatRequest
from app.services import chat_service
from app.services.conversation_service import require_conversation_owner
from app.services.inference.llm.errors import LLMGenerationIncomplete, LLMRequestError
from app.core.security import verify_token

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)
_INCOMPLETE_MESSAGE = (
    "답변 생성이 끝까지 완료되지 않았습니다. 표시된 일부 내용은 검증·저장되지 않았으므로 "
    "근거로 사용하지 말고 질문을 나누어 다시 시도해주세요."
)


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

    tool_events = []
    try:
        answer, calculator = await chat_service.process_chat(
            query=body.query,
            conversation_id=str(conversation_id),
            user_id=user["id"],
            tool_events=tool_events,
        )
    except LLMRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.event()) from exc
    except LLMGenerationIncomplete as exc:
        raise HTTPException(status_code=502, detail={
            "code": "generation_incomplete",
            "message": _INCOMPLETE_MESSAGE,
            "reason": exc.reason,
        }) from exc
    return {"output": answer, "calculator": calculator,
            "tools": [e for e in tool_events if e["status"] not in {"selecting", "running"}]}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict = Depends(verify_token),
):
    """SSE 스트리밍 응답. tool/chunk/calc 이벤트와 저장 후 DONE을 전송한다."""
    # StreamingResponse가 헤더를 전송하기 전에 소유권을 확인해야 오류를
    # 정상적인 HTTP 404로 반환할 수 있다.
    pool = await get_pool()
    async with pool.acquire() as conn:
        conversation_id = await require_conversation_owner(
            conn, body.conversation_id, user["id"],
        )

    async def generate():
        try:
            async for event in chat_service.stream_chat_response(
                query=body.query,
                conversation_id=str(conversation_id),
                user_id=user["id"],
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except LLMRequestError as exc:
            yield f"data: {json.dumps(exc.event(), ensure_ascii=False)}\n\n"
            return
        except LLMGenerationIncomplete as exc:
            event = {
                "type": "error", "code": "generation_incomplete",
                "message": _INCOMPLETE_MESSAGE,
                "reason": exc.reason,
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            return
        except Exception as exc:
            logger.error("Chat stream failed: %s", type(exc).__name__)
            event = {"type": "error", "code": "stream_failed",
                     "message": "답변 생성 또는 저장에 실패했습니다. 잠시 후 다시 시도해 주세요."}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            return
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

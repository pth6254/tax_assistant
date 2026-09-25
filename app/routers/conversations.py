"""
routers/conversations.py — 대화 세션 관리 엔드포인트
GET    /api/conversations              내 대화 목록
POST   /api/conversations              새 대화 생성
GET    /api/conversations/{id}/messages 대화 메시지 조회
PATCH  /api/conversations/{id}         대화 제목 변경
DELETE /api/conversations/{id}         대화 삭제
"""
import json
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import get_pool
from app.core.security import verify_token
from app.services.conversation_service import require_conversation_owner

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


class RenameRequest(BaseModel):
    title: str


class ReviseRequest(BaseModel):
    expected_message_id: int = Field(gt=0)
    query: str | None = Field(default=None, min_length=1, max_length=10000)


class RegenerateRequest(BaseModel):
    expected_message_id: int = Field(gt=0)
    expected_version: int = Field(gt=0)


class SelectVersionRequest(RegenerateRequest):
    version: int = Field(gt=0)


@router.post('/{conv_id}/revise', status_code=201)
async def revise_conversation(conv_id: str, body: ReviseRequest, user: dict = Depends(verify_token)):
    from app.services.chat_revision_service import fork_last_turn
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await fork_last_turn(conn, conv_id, user['id'], body.expected_message_id, body.query)


@router.post('/{conv_id}/regenerate')
async def regenerate_answer(conv_id: str, body: RegenerateRequest, user: dict = Depends(verify_token)):
    from app.services.answer_version_service import prepare_regeneration
    from app.services.chat_service import stream_chat_response
    from app.services.inference.llm.errors import LLMGenerationIncomplete, LLMRequestError
    pool = await get_pool()
    async with pool.acquire() as conn:
        cid, regeneration = await prepare_regeneration(
            conn, conv_id, user['id'], body.expected_message_id, body.expected_version)

    async def generate():
        try:
            async for event in stream_chat_response(regeneration.query, str(cid), user['id'], regeneration=regeneration):
                yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
        except LLMRequestError as exc:
            yield f'data: {json.dumps(exc.event(), ensure_ascii=False)}\n\n'
            return
        except (LLMGenerationIncomplete, HTTPException, ValueError) as exc:
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield f'data: {json.dumps({"type": "error", "message": message}, ensure_ascii=False)}\n\n'
            return
        except Exception as exc:
            logger.error('Answer regeneration failed: %s', type(exc).__name__)
            event = {'type': 'error', 'code': 'regeneration_failed',
                     'message': '답변 재생성 또는 저장에 실패했습니다. 기존 답변은 유지됩니다.'}
            yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
            return
        yield 'data: [DONE]\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.put('/{conv_id}/answers/{message_id}/version')
async def choose_answer_version(conv_id: str, message_id: int, body: SelectVersionRequest,
                                user: dict = Depends(verify_token)):
    from app.services.answer_version_service import select_version
    if message_id != body.expected_message_id:
        raise HTTPException(422, '답변 메시지 ID가 일치하지 않습니다.')
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await select_version(conn, conv_id, user['id'], message_id, body.version, body.expected_version)


@router.get("")
async def list_conversations(user: dict = Depends(verify_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id, c.title, c.created_at, c.updated_at,
                (
                    SELECT cl.message->>'content'
                    FROM   chat_logs cl
                    WHERE  cl.conversation_id = c.id
                      AND  cl.message->>'role' = 'assistant'
                    ORDER BY cl.created_at DESC
                    LIMIT 1
                ) AS preview
            FROM conversations c
            WHERE c.user_id = $1
            ORDER BY c.updated_at DESC
            LIMIT 50
            """,
            _uuid.UUID(user["id"]),
        )
    return [
        {
            "id":         str(r["id"]),
            "title":      r["title"],
            "created_at": r["created_at"].isoformat(),
            "updated_at": r["updated_at"].isoformat(),
            "preview":    (r["preview"] or "")[:60] if r["preview"] else "",
        }
        for r in rows
    ]


@router.post("", status_code=201)
async def create_conversation(user: dict = Depends(verify_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO conversations (user_id) VALUES ($1) RETURNING id, title, created_at, updated_at",
            _uuid.UUID(user["id"]),
        )
    return {
        "id":         str(row["id"]),
        "title":      row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "preview":    "",
    }


@router.get("/{conv_id}/messages")
async def get_messages(conv_id: str, user: dict = Depends(verify_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        cid = await require_conversation_owner(conn, conv_id, user["id"])
        rows = await conn.fetch(
            """SELECT cl.id, cl.message, cl.answer_version,
                      (SELECT COUNT(*) FROM chat_answer_versions v WHERE v.assistant_message_id=cl.id) AS version_count
               FROM chat_logs cl WHERE cl.conversation_id = $1 ORDER BY cl.id ASC""",
            cid,
        )
    result = []
    for r in rows:
        msg = r["message"]
        if isinstance(msg, str):
            msg = json.loads(msg)
        result.append({"message_id": r.get('id'), "role": msg["role"], "content": msg["content"],
                       "tools": msg.get("tools", []),
                       "answer_version": r.get('answer_version', 1) if msg['role'] == 'assistant' else None,
                       "answer_version_count": max(1, r.get('version_count', 0)) if msg['role'] == 'assistant' else None})
    return result


@router.patch("/{conv_id}")
async def rename_conversation(
    conv_id: str,
    body: RenameRequest,
    user: dict = Depends(verify_token),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        cid = await require_conversation_owner(conn, conv_id, user["id"])
        await conn.execute(
            "UPDATE conversations SET title = $1, updated_at = now() WHERE id = $2",
            body.title[:50], cid,
        )
    return {"message": "제목이 변경되었습니다."}


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(verify_token)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        cid = await require_conversation_owner(conn, conv_id, user["id"])
        await conn.execute("DELETE FROM chat_logs    WHERE conversation_id = $1", cid)
        await conn.execute("DELETE FROM conversations WHERE id = $1", cid)
    return {"message": "대화가 삭제되었습니다."}

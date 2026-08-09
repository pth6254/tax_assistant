"""
routers/conversations.py — 대화 세션 관리 엔드포인트
GET    /api/conversations              내 대화 목록
POST   /api/conversations              새 대화 생성
GET    /api/conversations/{id}/messages 대화 메시지 조회
PATCH  /api/conversations/{id}         대화 제목 변경
DELETE /api/conversations/{id}         대화 삭제
"""
import json
import uuid as _uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_pool
from app.core.security import verify_token
from app.services.conversation_service import require_conversation_owner

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class RenameRequest(BaseModel):
    title: str


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
            "SELECT message FROM chat_logs WHERE conversation_id = $1 ORDER BY created_at ASC",
            cid,
        )
    result = []
    for r in rows:
        msg = r["message"]
        if isinstance(msg, str):
            msg = json.loads(msg)
        result.append({"role": msg["role"], "content": msg["content"]})
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

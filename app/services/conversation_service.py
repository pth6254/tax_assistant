"""Conversation access-control helpers shared by API routers."""

import uuid as _uuid

from fastapi import HTTPException


_NOT_FOUND_DETAIL = "대화를 찾을 수 없습니다."


async def require_conversation_owner(
    conn,
    conversation_id: str | _uuid.UUID,
    user_id: str | _uuid.UUID,
) -> _uuid.UUID:
    """Return the conversation UUID only when it belongs to the current user.

    Missing, malformed, and foreign conversation IDs intentionally produce the
    same 404 response so callers cannot use this endpoint to enumerate IDs.
    """
    try:
        conv_id = _uuid.UUID(str(conversation_id))
        owner_id = _uuid.UUID(str(user_id))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from None

    exists = await conn.fetchval(
        "SELECT id FROM conversations WHERE id = $1 AND user_id = $2",
        conv_id,
        owner_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    return conv_id

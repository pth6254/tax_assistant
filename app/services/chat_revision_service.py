"""Preserve an original conversation while revising its last completed turn."""
import json
import uuid
from fastapi import HTTPException
from app.services.conversation_service import require_conversation_owner


def last_turn(rows, expected_id):
    if len(rows) != 2:
        raise HTTPException(409, '완료된 마지막 대화만 수정할 수 있습니다.')
    messages = [json.loads(r['message']) if isinstance(r['message'], str) else r['message'] for r in rows]
    if (rows[0]['id'] != expected_id or messages[0]['role'] != 'assistant'
            or messages[1]['role'] != 'user'):
        raise HTTPException(409, '대화가 변경되었습니다. 새로고침 후 다시 시도하세요.')
    return rows[1]['id'], messages[1]['content']


async def fork_last_turn(conn, conversation_id, user_id, expected_id, query=None):
    async with conn.transaction():
        cid = await require_conversation_owner(conn, conversation_id, user_id)
        rows = await conn.fetch('SELECT id, message FROM chat_logs WHERE conversation_id=$1 ORDER BY id DESC LIMIT 2', cid)
        cutoff, original_query = last_turn(rows, expected_id)
        question = original_query if query is None else query.strip()
        if not question:
            raise HTTPException(422, '질문을 입력하세요.')
        new_id = await conn.fetchval(
            'INSERT INTO conversations (user_id, title) VALUES ($1, $2) RETURNING id',
            uuid.UUID(user_id), ('다시 답변 · ' + question)[:50])
        await conn.execute('''INSERT INTO chat_logs (conversation_id, message, created_at)
            SELECT $1, message, created_at FROM chat_logs
            WHERE conversation_id=$2 AND id < $3 ORDER BY id''', new_id, cid, cutoff)
    return {'id':str(new_id), 'query':question, 'original_id':str(cid)}

"""Version the last assistant turn without duplicating its user question."""
import json
from dataclasses import dataclass

from fastapi import HTTPException
from config import MEMORY_TURNS

from app.services.chat_revision_service import last_turn
from app.services.conversation_service import require_conversation_owner


@dataclass(frozen=True)
class Regeneration:
    message_id: int
    expected_version: int
    query: str
    history: list[dict]


def _message(value):
    return json.loads(value) if isinstance(value, str) else value


async def prepare_regeneration(conn, conversation_id, user_id, message_id, expected_version):
    cid = await require_conversation_owner(conn, conversation_id, user_id)
    rows = await conn.fetch(
        'SELECT id, message, answer_version FROM chat_logs WHERE conversation_id=$1 ORDER BY id DESC LIMIT 2', cid)
    user_message_id, query = last_turn(rows, message_id)
    if rows[0]['answer_version'] != expected_version:
        raise HTTPException(409, '답변 버전이 변경되었습니다. 대화를 새로고침한 뒤 다시 시도하세요.')
    earlier = await conn.fetch(
        'SELECT message FROM chat_logs WHERE conversation_id=$1 AND id<$2 ORDER BY id DESC LIMIT $3',
        cid, user_message_id, MEMORY_TURNS * 2)
    history = []
    for row in reversed(earlier):
        msg = _message(row['message'])
        entry = {'role': msg['role'], 'content': msg['content']}
        for tool in msg.get('tools', []):
            if tool.get('tool') == 'history_lookup' and tool.get('history_context'):
                entry['history_context'] = tool['history_context']
        history.append(entry)
    return cid, Regeneration(message_id, expected_version, query, history)


async def _locked_last_turn(conn, cid, message_id, expected_version):
    # Lock the conversation, not the answer while model inference runs. All version writes
    # serialize here and are checked again against the latest completed turn.
    await conn.fetchrow('SELECT id FROM conversations WHERE id=$1 FOR UPDATE', cid)
    rows = await conn.fetch(
        'SELECT id, message, answer_version FROM chat_logs WHERE conversation_id=$1 ORDER BY id DESC LIMIT 2', cid)
    last_turn(rows, message_id)
    if rows[0]['answer_version'] != expected_version:
        raise HTTPException(409, '답변 버전이 변경되었습니다. 대화를 새로고침한 뒤 다시 시도하세요.')
    return _message(rows[0]['message'])


async def commit_regeneration(conn, cid, regen, answer, tools):
    if not answer.strip():
        raise HTTPException(502, '빈 답변은 버전으로 저장할 수 없습니다.')
    async with conn.transaction():
        previous = await _locked_last_turn(conn, cid, regen.message_id, regen.expected_version)
        await conn.execute(
            '''INSERT INTO chat_answer_versions (assistant_message_id, version, message)
               VALUES ($1,$2,$3::jsonb) ON CONFLICT DO NOTHING''',
            regen.message_id, regen.expected_version, json.dumps(previous, ensure_ascii=False))
        new_version = (await conn.fetchval(
            'SELECT COALESCE(MAX(version), 0) + 1 FROM chat_answer_versions WHERE assistant_message_id=$1',
            regen.message_id))
        message = {'role': 'assistant', 'content': answer}
        if tools:
            message['tools'] = tools
        await conn.execute(
            'INSERT INTO chat_answer_versions (assistant_message_id, version, message) VALUES ($1,$2,$3::jsonb)',
            regen.message_id, new_version, json.dumps(message, ensure_ascii=False))
        await conn.execute(
            'UPDATE chat_logs SET message=$1::jsonb, answer_version=$2 WHERE id=$3',
            json.dumps(message, ensure_ascii=False), new_version, regen.message_id)
        await conn.execute('UPDATE conversations SET updated_at=now() WHERE id=$1', cid)
    return new_version


async def select_version(conn, conversation_id, user_id, message_id, version, expected_version):
    cid = await require_conversation_owner(conn, conversation_id, user_id)
    async with conn.transaction():
        await _locked_last_turn(conn, cid, message_id, expected_version)
        row = await conn.fetchrow(
            'SELECT message FROM chat_answer_versions WHERE assistant_message_id=$1 AND version=$2',
            message_id, version)
        if row is None:
            raise HTTPException(404, '요청한 답변 버전이 없습니다.')
        await conn.execute('UPDATE chat_logs SET message=$1::jsonb, answer_version=$2 WHERE id=$3',
                           json.dumps(_message(row['message']), ensure_ascii=False), version, message_id)
        await conn.execute('UPDATE conversations SET updated_at=now() WHERE id=$1', cid)
    return {'version': version}

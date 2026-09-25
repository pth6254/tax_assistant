import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.answer_version_service import (
    Regeneration, commit_regeneration, prepare_regeneration, select_version,
)


def _transaction(conn):
    tx = MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    conn.transaction = MagicMock(return_value=tx)


@pytest.mark.asyncio
async def test_prepare_excludes_current_pair_and_preserves_context():
    conn = AsyncMock()
    cid = uuid.uuid4()
    conn.fetch.side_effect = [
        [{'id': 4, 'answer_version': 2, 'message': {'role': 'assistant', 'content': 'answer'}},
         {'id': 3, 'answer_version': 1, 'message': {'role': 'user', 'content': 'question'}}],
        [{'message': {'role': 'assistant', 'content': 'prior answer'}},
         {'message': {'role': 'user', 'content': 'prior question'}}],
    ]
    with patch('app.services.answer_version_service.require_conversation_owner', AsyncMock(return_value=cid)):
        _, regen = await prepare_regeneration(conn, str(cid), str(uuid.uuid4()), 4, 2)
    assert regen.query == 'question'
    assert [m['content'] for m in regen.history] == ['prior question', 'prior answer']
    assert 'id<$2' in conn.fetch.call_args_list[1].args[0]


@pytest.mark.asyncio
async def test_stale_version_rejected_without_write():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {'id': 4, 'answer_version': 2, 'message': {'role': 'assistant', 'content': 'answer'}},
        {'id': 3, 'answer_version': 1, 'message': {'role': 'user', 'content': 'question'}}]
    with patch('app.services.answer_version_service.require_conversation_owner', AsyncMock(return_value=uuid.uuid4())):
        with pytest.raises(HTTPException) as err:
            await prepare_regeneration(conn, str(uuid.uuid4()), str(uuid.uuid4()), 4, 1)
    assert err.value.status_code == 409
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_regeneration_keeps_original_and_allocates_after_max_version():
    conn = AsyncMock()
    _transaction(conn)
    conn.fetch.return_value = [
        {'id': 4, 'answer_version': 1, 'message': {'role': 'assistant', 'content': 'original'}},
        {'id': 3, 'answer_version': 1, 'message': {'role': 'user', 'content': 'question'}}]
    conn.fetchval.return_value = 4
    cid = uuid.uuid4()
    version = await commit_regeneration(conn, cid, Regeneration(4, 1, 'question', []), 'new', [])
    assert version == 4
    inserts = [call.args for call in conn.execute.call_args_list if 'INSERT INTO chat_answer_versions' in call.args[0]]
    assert len(inserts) == 2
    assert json.loads(inserts[0][3])['content'] == 'original'
    assert json.loads(inserts[1][3])['content'] == 'new'
    assert inserts[1][2] == 4


@pytest.mark.asyncio
async def test_select_version_reuses_saved_answer():
    conn = AsyncMock()
    _transaction(conn)
    conn.fetch.return_value = [
        {'id': 4, 'answer_version': 3, 'message': {'role': 'assistant', 'content': 'current'}},
        {'id': 3, 'answer_version': 1, 'message': {'role': 'user', 'content': 'question'}}]
    conn.fetchrow.side_effect = [{'id': uuid.uuid4()}, {'message': {'role': 'assistant', 'content': 'old'}}]
    with patch('app.services.answer_version_service.require_conversation_owner', AsyncMock(return_value=uuid.uuid4())):
        result = await select_version(conn, str(uuid.uuid4()), str(uuid.uuid4()), 4, 1, 3)
    assert result == {'version': 1}
    update = [call.args for call in conn.execute.call_args_list if 'UPDATE chat_logs' in call.args[0]][0]
    assert json.loads(update[1])['content'] == 'old'
    assert update[2] == 1


def test_answer_version_endpoints_require_auth(client):
    assert client.post('/api/conversations/test/regenerate', json={'expected_message_id': 4, 'expected_version': 1}).status_code == 401
    assert client.put('/api/conversations/test/answers/4/version', json={
        'expected_message_id': 4, 'expected_version': 1, 'version': 1}).status_code == 401


def test_regeneration_provider_error_is_reported_without_false_done(client, auth_cookie):
    cid = uuid.uuid4()

    async def fake_stream(query, conversation_id, user_id, regeneration):
        yield {'type': 'chunk', 'text': 'partial'}
        raise RuntimeError('private upstream detail')

    with patch('app.services.answer_version_service.prepare_regeneration',
               AsyncMock(return_value=(cid, Regeneration(4, 1, 'question', [])))), \
         patch('app.services.chat_service.stream_chat_response', fake_stream):
        resp = client.post(f'/api/conversations/{cid}/regenerate',
                           json={'expected_message_id': 4, 'expected_version': 1}, cookies=auth_cookie)
    assert resp.status_code == 200
    assert '"code": "regeneration_failed"' in resp.text
    assert 'private upstream detail' not in resp.text
    assert '[DONE]' not in resp.text


@pytest.mark.asyncio
async def test_regeneration_stream_commits_after_final_chunk(monkeypatch):
    from app.services import chat_service

    class Chain:
        async def astream(self, _values):
            yield 'fresh answer'

    conn = AsyncMock()
    acquire = MagicMock(__aenter__=AsyncMock(return_value=conn),
                        __aexit__=AsyncMock(return_value=False))
    pool = MagicMock()
    pool.acquire.return_value = acquire
    monkeypatch.setattr(chat_service, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(chat_service, 'needs_history', lambda _query: False)
    monkeypatch.setattr(chat_service, 'history_route', lambda _query, _history: None)
    monkeypatch.setattr(chat_service, '_fetch_rag_and_web_context',
                        AsyncMock(return_value=('', '', [], None)))
    monkeypatch.setattr(chat_service, 'streaming_chain', lambda *args, **kwargs: Chain())
    monkeypatch.setattr(chat_service, '_append_source_list_if_missing', AsyncMock(side_effect=lambda answer, _: answer))
    monkeypatch.setattr(chat_service, '_correct_source_titles', AsyncMock(side_effect=lambda answer: answer))
    monkeypatch.setattr(chat_service, 'build_citation_footer', lambda *args: '')
    commit = AsyncMock(return_value=2)
    regen = Regeneration(4, 1, 'question', [])
    with patch('app.services.answer_version_service.commit_regeneration', commit):
        events = [event async for event in chat_service.stream_chat_response(
            'question', str(uuid.uuid4()), str(uuid.uuid4()), regeneration=regen)]
    assert events == [{'type': 'chunk', 'text': 'fresh answer'}]
    assert commit.await_args.args[2:] == (regen, 'fresh answer', [])

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from app.services.chat_revision_service import last_turn, fork_last_turn


def rows():
    return [{'id':4,'message':{'role':'assistant','content':'old answer'}},
            {'id':3,'message':{'role':'user','content':'old query'}}]


def test_only_latest_completed_pair():
    assert last_turn(rows(), 4) == (3, 'old query')
    for data, expected in [(rows(),2),([],4),(rows()[::-1],4)]:
        with pytest.raises(HTTPException) as e:
            last_turn(data, expected)
        assert e.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected', [(None,'old query'),(' edited ','edited')])
async def test_fork_preserves_original_and_excludes_last_pair(query, expected):
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock()
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    conn.fetch.return_value = rows()
    new_id, source, user = uuid.uuid4(), uuid.uuid4(), str(uuid.uuid4())
    conn.fetchval.return_value = new_id
    with patch('app.services.chat_revision_service.require_conversation_owner',AsyncMock(return_value=source)):
        result = await fork_last_turn(conn, str(source), user, 4, query)
    assert result['query'] == expected
    sql, destination, original, cutoff = conn.execute.call_args.args
    assert 'id < $3' in sql and 'DELETE' not in sql and 'UPDATE' not in sql
    assert (destination,original,cutoff) == (new_id,source,3)


@pytest.mark.asyncio
async def test_foreign_owner_cannot_copy():
    conn = AsyncMock()
    tx = MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    conn.transaction = MagicMock(return_value=tx)
    with patch('app.services.chat_revision_service.require_conversation_owner',AsyncMock(side_effect=HTTPException(404))):
        with pytest.raises(HTTPException):
            await fork_last_turn(conn, str(uuid.uuid4()),str(uuid.uuid4()),4)
    conn.fetch.assert_not_called()
    conn.execute.assert_not_called()


def test_revision_requires_auth(client):
    assert client.post('/api/conversations/test/revise', json={'expected_message_id':4}).status_code == 401

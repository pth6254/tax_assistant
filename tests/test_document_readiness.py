from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.services import upload_service


@pytest.mark.asyncio
@pytest.mark.parametrize('version,column', [('v1', 'embedding'), ('v2', 'embedding_v2')])
async def test_document_readiness_uses_active_vectors_and_owner(mock_pool, monkeypatch, version, column):
    pool, conn = mock_pool
    monkeypatch.setattr(upload_service, 'EMBEDDING_VERSION', version)
    rows = [dict(filename='test.pdf', law_name='test', category='test', chunk_count=2,
                 embedded_count=count, uploaded_at=None) for count in (0, 1, 2)]
    with patch.object(conn, 'fetch', AsyncMock(return_value=rows)) as fetch:
        with patch.object(upload_service, 'get_pool', AsyncMock(return_value=pool)):
            uid = '00000000-0000-0000-0000-000000000001'
            result = await upload_service.list_documents(uid)
    assert [item['search_ready'] for item in result] == [False, False, True]
    sql, owner = fetch.call_args.args
    assert f'COUNT({column})' in sql
    assert 'WHERE user_id = $1' in sql
    assert owner == UUID(uid)

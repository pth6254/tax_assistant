from datetime import date
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from app.services.graph import temporal_service as service


def node(key, published='20260501', effective='20260701'):
    return dict(key=key, law_name='시험법', article_no='제1조',
                amendment_date=published, effective_date=effective)


def test_publication_does_not_imply_effectiveness():
    assert service.prepare_snapshot([node('a')], [], date(2026, 6, 1))[1] == []
    assert len(service.prepare_snapshot([node('a')], [], date(2026, 7, 1))[1]) == 1


def test_unknown_and_unpublished_nodes_cannot_connect():
    nodes = [node('a'), node('b', published='20260801'), node('c', effective='bad')]
    edges = [dict(source='a', target='b', reference='제1조', evidence='인용')]
    _, selected, links = service.prepare_snapshot(nodes, edges, date(2026, 7, 1))
    assert len(selected) == 1
    assert links == []


def test_snapshot_identity_is_stable_and_date_specific():
    nodes = [node('a'), node('b')]
    a = service.prepare_snapshot(nodes, [], date(2026, 7, 1))[0]
    assert a == service.prepare_snapshot(nodes[::-1], [], date(2026, 7, 1))[0]
    assert a != service.prepare_snapshot(nodes, [], date(2026, 7, 2))[0]


def test_relation_change_creates_a_new_snapshot():
    nodes = [node('a'), node('b')]
    edge = dict(source='a', target='b', reference='제1조', evidence='인용')
    a = service.prepare_snapshot(nodes, [edge], date(2026, 7, 1))[0]
    assert a != service.prepare_snapshot(nodes, [], date(2026, 7, 1))[0]


@pytest.mark.asyncio
async def test_isolated_node_is_returned_without_invented_edges(monkeypatch):
    driver = AsyncMock()
    driver.execute_query.side_effect = [
        ([{'key': 'snapshot', 'recorded_at': '2026-07-01'}], None, None),
        ([{'source': {'key': 'node'}, 'edge': None, 'target': None}], None, None),
    ]
    @asynccontextmanager
    async def connect():
        yield driver
    monkeypatch.setattr(service, 'connect', connect)
    result = await service.query_snapshot('2026-07-01', '시험법', '제1조')
    assert result['status'] == 'observed'
    assert result['nodes'] == [{'key': 'node'}]
    assert result['edges'] == []


@pytest.mark.parametrize('value', ['2026-02-30', '2026/07/01', '', '202607011'])
def test_invalid_dates_rejected(value):
    with pytest.raises(ValueError):
        service.parse_date(value)


@pytest.mark.asyncio
async def test_unrecorded_date_never_falls_back_to_current(monkeypatch):
    driver = AsyncMock()
    driver.execute_query.return_value = ([], None, None)
    @asynccontextmanager
    async def connect():
        yield driver
    monkeypatch.setattr(service, 'connect', connect)
    result = await service.query_snapshot('2025-01-01', '시험법', '제1조')
    assert result['status'] == 'unknown'
    assert result['nodes'] == []
    assert result['legal_applicability_verified'] is False
    driver.execute_query.assert_awaited_once()

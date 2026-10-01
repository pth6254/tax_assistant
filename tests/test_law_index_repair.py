"""A repair cannot publish partial originals/indexes or overwrite new content."""
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.law import index_repair as repair
from app.services.evidence import digest, has_missing_items
from tests.conftest import _make_mock_pool
import config


def test_letter_list_in_official_body_is_not_truncation():
    text = '④ 국세청장은 다음 각 호의 어느 하나에 해당하는 경우 표준인증을 취소할 수 있다.\n가. 거짓이나 그 밖의 부정한 방법으로 표준인증을 받은 경우\n나. 조건을 충족하지 않는 경우'
    assert not has_missing_items(text)
    assert has_missing_items(text.split('\n', 1)[0])
    # A valid list in another paragraph cannot cover a genuinely missing list.
    assert has_missing_items(text + '\n⑤ 다음 각 호의 서류를 첨부한다.')


def candidate():
    text = '제1조(요건)\n① ' + '첫째 적용 요건. ' * 55 + '\n② ' + '둘째 제외 요건. ' * 55
    row = {'id': 17, 'law_name': '법인세법', 'law_type': '법률', 'tax_type': '법인세법',
           'article_no': '제1조', 'article_title': '요건', 'article_text': text,
           'content_hash': digest(text), 'effective_date': '2026-01-01',
           'amendment_date': '2025-12-01', 'source_url': 'https://law.go.kr/법령/법인세법',
           'is_current': True, 'index_metadata': {}, 'embedding': None, 'embedding_v2': None}
    return {'before': row, 'after': row | {'article_text': text + '\n추가 원문',
                                         'content_hash': digest(text + '\n추가 원문')},
            'snapshot_source_id': 'history_snapshot:1:제1조'}


async def prepared():
    item = candidate()
    embed = AsyncMock(side_effect=lambda texts: ([[1.0] * config.EMBED_DIM for _ in texts], None))
    return await repair.prepare_repair(item, embed, 'run-1')


@pytest.mark.asyncio
async def test_invalid_vectors_cannot_be_prepared():
    for vectors in ([[float('nan')] * config.EMBED_DIM] * 3, [[1.0, 2.0]] * 3, []):
        with pytest.raises(ValueError):
            await repair.prepare_repair(candidate(), AsyncMock(return_value=(vectors, None)), 'run-1')


@pytest.mark.asyncio
async def test_durable_backup_failure_happens_before_any_db_mutation():
    _, conn = _make_mock_pool()
    plan = await prepared()
    conn.fetchrow.return_value = plan.before
    conn.fetch.return_value = []
    with pytest.raises(OSError):
        await repair.apply_repair(conn, plan, Mock(side_effect=OSError('disk-full')))
    conn.execute.assert_not_called()
    conn.executemany.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_parent_change_is_not_overwritten():
    _, conn = _make_mock_pool()
    plan = await prepared()
    conn.fetchrow.return_value = plan.before | {'content_hash': 'new-source'}
    backup = Mock()
    with pytest.raises(ValueError, match='repair_parent_changed'):
        await repair.apply_repair(conn, plan, backup)
    backup.assert_not_called()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_body_and_clauses_share_transaction_and_actual_input_lineage():
    _, conn = _make_mock_pool()
    plan = await prepared()
    conn.fetchrow.return_value = plan.before
    conn.fetch.return_value = []
    saved = Mock()
    await repair.apply_repair(conn, plan, saved)
    assert saved.call_args.args[0]['article']['content_hash'] == plan.before['content_hash']
    conn.transaction.return_value.__aenter__.assert_awaited_once()
    assert plan.metadata['source_hash'] == plan.after['content_hash']
    assert len(plan.clauses) == 2
    assert all(c[-1]['source_hash'] == plan.after['content_hash'] for c in plan.clauses)
    assert len({plan.metadata['input_hash'], *(c[-1]['input_hash'] for c in plan.clauses)}) == 3
    assert conn.execute.await_args_list[0].args[6] is None


@pytest.mark.asyncio
async def test_clause_write_failure_rolls_back_body_transaction():
    _, conn = _make_mock_pool()
    plan = await prepared()
    conn.fetchrow.return_value = plan.before
    conn.fetch.return_value = []
    conn.executemany.side_effect = RuntimeError('write-failed')
    with pytest.raises(RuntimeError):
        await repair.apply_repair(conn, plan, Mock())
    assert conn.transaction.return_value.__aexit__.await_args.args[0] is RuntimeError


@pytest.mark.asyncio
async def test_rollback_cannot_overwrite_later_repair():
    _, conn = _make_mock_pool()
    conn.fetchrow.return_value = candidate()['after'] | {'index_metadata': {'repair_run_id': 'another-run'}}
    with pytest.raises(ValueError, match='rollback_parent_changed'):
        await repair.restore_backup(conn, {'article': candidate()['before'], 'clauses': []},
                                    candidate()['after']['content_hash'], 'run-1')
    conn.execute.assert_not_called()

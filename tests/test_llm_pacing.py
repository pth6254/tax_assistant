import asyncio
import pytest
from app.services.inference.llm import pacing


@pytest.mark.asyncio
async def test_all_task_clients_share_the_same_account_model_limit(monkeypatch):
    now = [100.0]
    delays = []
    monkeypatch.setattr(pacing, 'monotonic', lambda: now[0])
    async def sleep(delay):
        delays.append(delay)
        now[0] += delay
    monkeypatch.setattr(pacing, 'sleep', sleep)
    key = ('endpoint', 'model', 'credential_digest')
    await asyncio.gather(*(pacing.wait_for_slot(key, 20) for _ in range(4)))
    assert delays == [3.0, 3.0, 3.0]
    await pacing.wait_for_slot(('endpoint', 'other_model', 'credential_digest'), 20)
    assert len(delays) == 3


@pytest.mark.asyncio
async def test_cancelled_wait_releases_lock_and_does_not_reserve_slot(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(pacing, 'monotonic', lambda: now[0])
    gate = asyncio.Event()
    async def sleep(delay):
        gate.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(pacing, 'sleep', sleep)
    limiter = pacing.RequestPacer(20)
    await limiter.acquire()
    task = asyncio.create_task(limiter.acquire())
    await gate.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not limiter.lock.locked() and limiter.next_start == 103.0


@pytest.mark.asyncio
async def test_zero_disables_pacing(monkeypatch):
    async def fail(_):
        raise AssertionError('must not wait')
    monkeypatch.setattr(pacing, 'sleep', fail)
    await pacing.wait_for_slot(('endpoint', 'model', 'digest'), 0)

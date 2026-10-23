"""The answer stream keeps proxies from closing it while an answer is being checked."""
import asyncio

import pytest

from app.core.sse import HEARTBEAT, with_heartbeat


@pytest.mark.asyncio
async def test_a_silent_stretch_sends_heartbeats_and_events_pass_through_in_order():
    async def slow():
        yield {"type": "verification", "status": "planning"}
        await asyncio.sleep(0.25)
        yield {"type": "chunk", "text": "답"}
    seen = [event async for event in with_heartbeat(slow(), interval=0.1)]
    assert seen[0] == {"type": "verification", "status": "planning"} and seen[-1] == {"type": "chunk", "text": "답"}
    assert seen.count(HEARTBEAT) >= 1 and HEARTBEAT.startswith(":")   # an SSE comment, ignored by clients


@pytest.mark.asyncio
async def test_an_error_in_the_answer_reaches_the_route_as_before():
    async def failing():
        yield {"type": "verification", "status": "planning"}
        raise ValueError("stored answer changed")
    stream = with_heartbeat(failing(), interval=1)
    assert await anext(stream) == {"type": "verification", "status": "planning"}
    with pytest.raises(ValueError, match="stored answer changed"):
        await anext(stream)


@pytest.mark.asyncio
async def test_a_client_that_leaves_cancels_the_answer():
    cancelled = asyncio.Event()

    async def long_answer():
        try:
            yield {"type": "verification", "status": "planning"}
            await asyncio.sleep(30)
            yield {"type": "chunk", "text": "never"}
        finally:
            cancelled.set()
    stream = with_heartbeat(long_answer(), interval=5)
    await anext(stream)
    await stream.aclose()
    await asyncio.wait_for(cancelled.wait(), timeout=1)

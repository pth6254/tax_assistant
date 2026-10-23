"""Server-sent events that stay open behind proxies while an answer is checked.

Vercel's proxy closes a response that sends nothing for 120 seconds, and a checked answer can be
silent longer than that between progress events. A comment line every 15 seconds keeps it open;
clients ignore SSE comments.
"""
import asyncio

HEARTBEAT = ": keep-alive\n\n"
_DONE = object()


class _Raised:
    def __init__(self, error):
        self.error = error


async def with_heartbeat(events, interval: float = 15.0):
    """Yield the events of `events`, and HEARTBEAT whenever none arrives within `interval` seconds.

    The source generator runs in one task from start to end, so context it sets (tracing runs,
    per-request variables) stays valid across its yields. Its exceptions are re-raised here, and
    closing this generator (a client disconnect) cancels it.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        try:
            async for item in events:
                await queue.put(item)
        except Exception as error:   # handed to the consumer, which handles it as before
            await queue.put(_Raised(error))
        finally:
            queue.put_nowait(_DONE)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield HEARTBEAT
                continue
            if item is _DONE:
                return
            if isinstance(item, _Raised):
                raise item.error
            yield item
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

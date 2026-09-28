"""Space remote calls across task-specific clients in the single API worker."""
import asyncio
from time import monotonic
from weakref import WeakKeyDictionary

sleep = asyncio.sleep
_by_loop = WeakKeyDictionary()


class RequestPacer:
    def __init__(self, rpm):
        self.interval = 60 / rpm
        self.lock = asyncio.Lock()
        self.next_start = 0.0

    async def acquire(self):
        async with self.lock:
            delay = self.next_start - monotonic()
            if delay > 0:
                await sleep(delay)
            # Cancellation before a request does not reserve a future slot.
            self.next_start = monotonic() + self.interval


async def wait_for_slot(key, rpm):
    if rpm <= 0:
        return
    group = _by_loop.setdefault(asyncio.get_running_loop(), {})
    pacer = group.setdefault((key, rpm), RequestPacer(rpm))
    await pacer.acquire()

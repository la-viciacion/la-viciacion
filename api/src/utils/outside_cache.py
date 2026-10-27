"""An in-memory cache for what the outside world answers (RAWG's series, Steam's and RAWG's pages of a game).

Nothing is stored in the database: each worker keeps the answers it got for `seconds` (and forgets them when it restarts).
A fetch that fails answers None, and that is remembered for `failure_seconds` only, so a page opened again and again does not
ask every time and a service that comes back is noticed soon. Simultaneous requests for the same key ask once, and a caller
that goes away does not cancel the others' answer. The cache holds at most `max_items`: the answer that expires first goes.
An answer that is there but misses something because one of several services failed is wrapped in `Partial`: it is used,
and remembered only for `failure_seconds`, so the missing part is asked again soon instead of tomorrow."""
import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable


class Partial:
    """What a fetch returns when its answer is usable but incomplete."""

    def __init__(self, value):
        self.value = value


class OutsideCache:
    def __init__(self, seconds: float, failure_seconds: float, max_items: int = 500):
        self.seconds = seconds
        self.failure_seconds = failure_seconds
        self.max_items = max_items
        self._items: dict[Hashable, tuple[float, object]] = {}  # key -> (when it expires, the answer or None if it failed)
        self._asking: dict[Hashable, asyncio.Task] = {}  # the answer being fetched

    async def get(self, key: Hashable, fetch: Callable[[], Awaitable[object]]):
        """The answer for `key` from memory while it is fresh, else `await fetch()` (None when the service failed)."""
        cached = self._items.get(key)
        if cached and cached[0] > time.time():
            return cached[1]
        if key not in self._asking:
            self._asking[key] = asyncio.create_task(self._ask(key, fetch))
        return await asyncio.shield(self._asking[key])  # shielded: the task goes on if this caller is cancelled

    async def _ask(self, key: Hashable, fetch: Callable[[], Awaitable[object]]):
        try:
            value = await fetch()
        finally:
            del self._asking[key]
        if isinstance(value, Partial):
            value = value.value
            self._remember(key, value, self.failure_seconds)
        else:
            self._remember(key, value, self.seconds if value is not None else self.failure_seconds)
        return value

    def _remember(self, key: Hashable, value: object, seconds: float) -> None:
        if key not in self._items and len(self._items) >= self.max_items:
            del self._items[min(self._items, key=lambda k: self._items[k][0])]
        self._items[key] = (time.time() + seconds, value)

    def clear(self) -> None:
        """Forget everything (the tests, and anybody who changes the key)."""
        self._items.clear()

"""A small in-memory cache for answers that are expensive to derive and hardly change (the group's library, its cost per
hour). Each worker keeps its own and forgets everything when it restarts; an answer is reused for `seconds` and recomputed
after that, so there is nothing to invalidate and the worst case is a figure that is a couple of minutes old."""
import threading
import time

_caches: list["TtlCache"] = []


class TtlCache:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._items: dict = {}
        self._lock = threading.Lock()  # held while computing, so a burst of requests derives the answer once
        _caches.append(self)

    def get(self, key, compute):
        """The answer for `key`, from the cache while it is fresh, else `compute()` (which must not be mutated by callers)."""
        with self._lock:
            found = self._items.get(key)
            if found and found[0] > time.monotonic():
                return found[1]
            value = compute()
            self._items[key] = (time.monotonic() + self.seconds, value)
            return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def clear_all() -> None:
    """Empties every cache (tests, and anything that has to be seen at once)."""
    for cache in _caches:
        cache.clear()

"""Failed-attempt limiter for the public endpoints (login, sign-up).

In memory and per process: enough for a single API replica (see docs/architecture.md);
a restart forgets the counters. Time is passed in so it is testable without clocks.

Two limiters are used for the login: one per account name (stops guessing one
password) and a looser one per client address. Behind the nginx proxy the client
address may be the proxy's, in which case the second one simply acts as a global
cap on failed logins, which is fine for a small private app.
"""
import threading
import time
from collections import deque

MAX_KEYS = 10000  # bound the memory an attacker can make us use with random names


class AttemptLimiter:
    def __init__(self, max_failures: int, window_seconds: int, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        while failures and now - failures[0] >= self.window:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return deque()
        return failures

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again (0 = not blocked)."""
        with self._lock:
            now = self._clock()
            failures = self._recent(key, now)
            if len(failures) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - failures[0])) + 1)

    def fail(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            if key not in self._failures and len(self._failures) >= MAX_KEYS:
                for stale in [k for k in self._failures if not self._recent(k, now)]:
                    self._failures.pop(stale, None)
                if len(self._failures) >= MAX_KEYS:
                    self._failures.pop(next(iter(self._failures)))
            failures = self._recent(key, now) or self._failures.setdefault(key, deque())
            failures.append(now)
            self._failures[key] = failures

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

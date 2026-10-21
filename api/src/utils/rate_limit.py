"""Failed-attempt limiter for the public login endpoint, and the usage limiter of the chat (UsageLimiter, below).

In memory and per process: enough for a single API replica (see docs/desarrollo/architecture.md);
a restart forgets the counters. Time is passed in so it is testable without clocks.

Two limiters are used for the login: one per account name (stops guessing one
password) and a looser one per client address. The per-client one is only used when
the API knows the real client address (see `client_key` in routers/basic.py); a
private peer such as the nginx container would put everybody in the same bucket.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Scope:
    """Whose use is counted (`key`: one user, or the whole group) and how much of it each window allows:
    `limits` is ((window in seconds, most uses), ...); a most of 0 or less leaves that window free."""

    key: str
    name: str  # what the refusal says it was ("user", "group")
    limits: tuple[tuple[int, int], ...]

    def active(self) -> tuple[tuple[int, int], ...]:
        return tuple((window, most) for window, most in self.limits if most > 0)


@dataclass(frozen=True)
class Refused:
    scope: str  # Scope.name
    window: int  # the window that was used up, in seconds (the one that takes longest to free if several are)
    wait: int  # seconds until it lets one more through


class UsageLimiter:
    """How many times something may be used (a question to the chat) per minute, hour and day, for a user and for the
    whole group at once.

    One list of times per key, whatever the windows: a use is counted in each window it is still inside, so the day
    is the last 24 hours, not the calendar day. A use is recorded only if every scope lets it through (one refused by
    the group does not eat the user's allowance). In memory and per process, like AttemptLimiter: enough for the single
    API replica, and a restart forgets the counts. Time is passed in so it is testable without clocks."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._uses: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _inside(self, key: str, now: float, horizon: int) -> deque:
        uses = self._uses.get(key)
        if uses is None:
            return deque()
        while uses and now - uses[0] >= horizon:
            uses.popleft()
        return uses

    def acquire(self, scopes: list[Scope]) -> Refused | None:
        """None if every scope allows one more use (it is recorded); else which one refuses and for how long (nothing is recorded)."""
        with self._lock:
            now = self._clock()
            for scope in scopes:
                limits = scope.active()
                if not limits:
                    continue
                uses = self._inside(scope.key, now, max(window for window, _ in limits))
                waits = []
                for window, most in limits:
                    recent = [t for t in uses if now - t < window]
                    if len(recent) >= most:
                        waits.append((int(window - (now - recent[len(recent) - most])) + 1, window))
                if waits:
                    wait, window = max(waits)
                    return Refused(scope.name, window, wait)
            for scope in scopes:
                if scope.active():
                    self._record(scope.key, now)
            return None

    def usage(self, scope: Scope) -> list[dict]:
        """For each window of the scope: its limit, the uses inside it and how many are left (None where it has no limit)."""
        with self._lock:
            now = self._clock()
            active = scope.active()
            uses = self._inside(scope.key, now, max(window for window, _ in active)) if active else deque()
            rows = []
            for window, most in scope.limits:
                used = sum(1 for t in uses if now - t < window) if most > 0 else None
                rows.append({"window": window, "limit": most if most > 0 else None, "used": used, "remaining": None if used is None else max(0, most - used)})
            return rows

    def _record(self, key: str, now: float) -> None:
        if key not in self._uses and len(self._uses) >= MAX_KEYS:
            self._uses.pop(next(iter(self._uses)))  # the oldest key: bounds the memory whatever the users
        self._uses.setdefault(key, deque()).append(now)

    def clear(self) -> None:
        with self._lock:
            self._uses.clear()

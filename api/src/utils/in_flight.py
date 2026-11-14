"""One question at a time for each player whose question the group's key pays.

What a question costs is known only when it ends, so the wallet and the monthly cap are checked against the calls that have already
finished. Without this, a player with a cent left could send several questions at once and every one would pass that check. With it
the most a player can pass their balance by is one question. A question paid with the player's own key spends nobody else's money
and is not held. The API is one process (the scheduler runs inside it), so a set in memory is enough: nothing is stored."""
import contextlib
import threading

from fastapi import HTTPException

from . import messages

_running: set[int] = set()
_lock = threading.Lock()


@contextlib.contextmanager
def one_at_a_time(user_id: int, own_key: bool):
    """Holds the player's place while their question runs; a second one at the same time is a 429 that says to wait."""
    if own_key:
        yield
        return
    with _lock:
        if user_id in _running:
            raise HTTPException(status_code=429, detail=messages.AI_BUSY)
        _running.add(user_id)
    try:
        yield
    finally:
        with _lock:
            _running.discard(user_id)

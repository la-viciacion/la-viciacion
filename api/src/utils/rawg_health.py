"""Is RAWG answering? RAWG is the backup of IGDB, and it has been down for days: every request to it waits for its timeout, and
what asks it only to complete something (an empty search, the extras of a game page, a resync) must not make the app wait
again and again. After a network failure RAWG is left alone for a while and whatever would ask it fails at once, as if it had
no key. A timeout or a refused connection is what counts: an error answer or a bad key is not a reason to stop asking."""
import time

PAUSE_SECONDS = 300

_paused_until = 0.0


class RawgPaused(ConnectionError):
    """RAWG failed a moment ago: it is not asked again yet."""


def paused() -> bool:
    return time.monotonic() < _paused_until


def failed() -> None:
    """RAWG did not answer: leave it alone for `PAUSE_SECONDS`."""
    global _paused_until
    _paused_until = time.monotonic() + PAUSE_SECONDS


def reset() -> None:
    """Ask again right away (the tests, and anybody who changes the key)."""
    global _paused_until
    _paused_until = 0.0

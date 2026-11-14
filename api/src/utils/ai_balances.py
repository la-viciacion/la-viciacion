"""The real balance of the accounts of the group's keys, for the providers that tell it (clients/provider_balance.py). Nothing is
stored (rule 2): it is asked when the admin opens the wallet and kept in memory a few minutes, so reloading the panel does not ask
the provider every time. A provider that fails shows its error and the others still answer."""
import threading
import time

from ..clients import provider_balance
from ..clients.ai_error import AIError
from . import ai_providers

CACHE_SECONDS = 300

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}  # provider -> (when it was asked, its answer)


def _ask(provider: str, key: str) -> dict:
    try:
        return {"provider": provider, **provider_balance.BALANCES[provider](key)}
    except AIError as e:
        return {"provider": provider, "error": str(e)}


def summary(refresh: bool = False) -> list[dict]:
    """One entry per provider that has a key in the .env and a balance to ask, in the order of the providers. Blocking: call it from a
    worker thread. `refresh` asks again whatever is in memory."""
    found = []
    for provider in ai_providers.available():
        if provider not in provider_balance.BALANCES:
            continue
        now = time.monotonic()
        with _lock:
            hit = _cache.get(provider)
        if hit and not refresh and now - hit[0] < CACHE_SECONDS:
            found.append(hit[1])
            continue
        answer = _ask(provider, ai_providers.api_key(provider))
        if "error" not in answer:  # a failure is not worth remembering: the next open asks again
            with _lock:
                _cache[provider] = (now, answer)
        found.append(answer)
    return found


def clear() -> None:
    with _lock:
        _cache.clear()

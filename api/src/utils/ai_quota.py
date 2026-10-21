"""The audit log's record of the AI running out of quota.

The free tier of a provider has limits per minute and per day that nobody publishes as a table: the only way to learn
them is what the provider says when it refuses a call. Each refusal is turned into a `Quota` (clients/quota.py) and
reported here: one row of `audit_log` (event `ai_quota`, which quota, its limit, when to retry and what asked for it) and
a warning in the log (not an error: Sentry would turn every refusal into an event).

A quota that has run out refuses every call until it recovers, so the same one is written once per `DEDUP_SECONDS`
and the refusals in between are counted in the next row (`repeated`).
"""
import json
import threading
import time

from ..clients.ai_error import Quota
from ..database import models
from ..database.database import SessionLocal
from .logger import LogManager

logger = LogManager().get_logger()

DEDUP_SECONDS = 600
SYSTEM_USER = "sistema"

_lock = threading.Lock()
_last: dict[tuple, list] = {}  # (provider, model, kind, ids) -> [when it was written, refusals since then]


def _due(key: tuple, now: float) -> int | None:
    """None while this quota was reported less than DEDUP_SECONDS ago (and the refusal is counted); else the refusals
    that were left out since the last row."""
    with _lock:
        last = _last.get(key)
        if last and now - last[0] < DEDUP_SECONDS:
            last[1] += 1
            return None
        skipped = last[1] if last else 0
        _last[key] = [now, 0]
        return skipped


def report(quota: Quota, source: str, provider: str | None, model: str | None, now: float | None = None) -> bool:
    """Write the row for a refusal; False if it was left out as a repeat. `source` says who asked ("chat", "welcome",
    "notice:new_game", "ai_test"...). Never raises: the answer to whoever asked does not depend on the log."""
    skipped = _due((provider, model, quota.kind, quota.ids), time.monotonic() if now is None else now)
    if skipped is None:
        return False
    logger.warning(f"AI quota ran out ({source}, {provider}/{model}): {quota.describe()}")
    detail = {
        "source": source, "provider": provider, "model": model, "kind": quota.kind, "retry_after": quota.retry_after,
        "quotas": list(quota.ids), "limit": quota.limit, "message": quota.message, "repeated": skipped,
    }
    try:
        with SessionLocal() as db:
            db.add(models.AuditLog(
                username=SYSTEM_USER, method="SYSTEM", path=f"ai/{source}"[:255], entity="ai", status=429,
                event="ai_quota", detail=json.dumps(detail, ensure_ascii=False),
            ))
            db.commit()
    except Exception as e:
        logger.error("Error writing the audit log: " + str(e), exc_info=True)
    return True

"""What the AI has cost: OpenAI's billed spend of the last year, by month, by day and by line item.

Nothing is stored (rule 2): it is asked to OpenAI's Costs API (clients/openai_usage.py) and kept in memory for a few
minutes, so the panel opening again and again asks once. OpenAI only keeps a year of spend (it refuses an older start
date), so that is as far back as the panel can go. Only OpenAI for now: Google has no API for what was spent."""
import datetime
import threading
import time

from ..clients import openai_usage

CACHE_SECONDS = 600
HISTORY_DAYS = 364  # OpenAI refuses a start date older than 365 days (UTC): one day less, so the date changing in between cannot fail
PRECISION = 6  # a call of a small model costs a fraction of a cent

_lock = threading.Lock()
_cached: tuple[float, dict] | None = None  # (when it expires, the summary)


def _ranked(amounts: dict[str, float]) -> list[dict]:
    return [{"name": name, "amount": round(amount, PRECISION)} for name, amount in sorted(amounts.items(), key=lambda kv: (-kv[1], kv[0]))]


def summarize(buckets: list[dict]) -> dict:
    """The daily buckets of the Costs API as the panel shows them: the total, every month with its line items, and the
    days that cost something. Pure."""
    total, currency = 0.0, "usd"
    items: dict[str, float] = {}
    months: dict[str, dict] = {}
    days: dict[str, float] = {}
    for bucket in buckets:
        day = datetime.datetime.fromtimestamp(bucket["start_time"], tz=datetime.timezone.utc).date().isoformat()
        for result in bucket.get("results") or []:
            amount = result.get("amount") or {}
            value = float(amount.get("value") or 0)
            if not value:
                continue
            currency = amount.get("currency") or currency
            name = result.get("line_item") or "Sin desglosar"
            month = months.setdefault(day[:7], {"total": 0.0, "items": {}})
            month["total"] += value
            month["items"][name] = month["items"].get(name, 0.0) + value
            items[name] = items.get(name, 0.0) + value
            days[day] = days.get(day, 0.0) + value
            total += value
    return {
        "currency": currency,
        "total": round(total, PRECISION),
        "items": _ranked(items),
        "months": [
            {"month": key, "total": round(m["total"], PRECISION), "items": _ranked(m["items"])} for key, m in sorted(months.items())
        ],
        "days": [{"date": key, "total": round(value, PRECISION)} for key, value in sorted(days.items())],
    }


def first_day(now: datetime.datetime | None = None) -> int:
    """The start (unix seconds) of the oldest day OpenAI still has: midnight UTC, HISTORY_DAYS ago."""
    today = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(datetime.timezone.utc).date()
    start = datetime.datetime.combine(today - datetime.timedelta(days=HISTORY_DAYS), datetime.time(), tzinfo=datetime.timezone.utc)
    return int(start.timestamp())


def summary(admin_key: str, refresh: bool = False) -> dict:
    """The summary of everything spent, from memory while it is fresh. Blocks on the network: call it from a worker
    thread. Raises AIError if OpenAI refuses or does not answer."""
    global _cached
    with _lock:
        if not refresh and _cached and _cached[0] > time.time():
            return _cached[1]
        data = summarize(openai_usage.costs(admin_key, first_day()))
        _cached = (time.time() + CACHE_SECONDS, data)
        return data


def clear() -> None:
    """Forget what is kept (the tests, and anybody who changes the key)."""
    global _cached
    _cached = None

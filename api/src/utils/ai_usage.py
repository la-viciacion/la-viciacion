"""What the AI has cost: what a provider billed in the last year, by month, by day and by line item.

Nothing is stored (rule 2): it is asked to the provider's cost API and kept in memory for a few minutes, so the panel opening again
and again asks once. Two providers say what they billed, each with an admin key of its own: OpenAI (clients/openai_usage.py) and
Anthropic (clients/anthropic_usage.py, which returns the same shape). OpenAI only keeps a year of spend (it refuses an older start
date), so that is as far back as the panel goes. Google has no API for what was spent, and OpenRouter says what is left instead
(utils/ai_balances.py)."""
import datetime
import threading
import time

from ..clients import anthropic_usage, openai_usage

CACHE_SECONDS = 600
HISTORY_DAYS = 364  # OpenAI refuses a start date older than 365 days (UTC): one day less, so the date changing in between cannot fail
PRECISION = 6  # a call of a small model costs a fraction of a cent

# provider -> the setting that holds its admin key; looked up and called when asked (not bound here), so a test patches the client
ADMIN_KEYS = {"openai": "ai.openai_admin_key", "anthropic": "ai.anthropic_admin_key"}
_COSTS = {
    "openai": lambda key, start: openai_usage.costs(key, start),
    "anthropic": lambda key, start: anthropic_usage.costs(key, start),
}

_locks = {provider: threading.Lock() for provider in ADMIN_KEYS}  # one provider asking does not make the other wait
_cached: dict[str, tuple[float, dict]] = {}  # provider -> (when it expires, the summary)


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


def add_months(*lists: list[dict]) -> list[dict]:
    """Lists of monthly totals ([{month, total}]) as one, adding the months they share. Pure."""
    summed: dict[str, float] = {}
    for item in (item for months in lists for item in months):
        summed[item["month"]] = summed.get(item["month"], 0.0) + float(item["total"])
    return [{"month": month, "total": total} for month, total in summed.items()]


def rollup(months: list[dict], today: datetime.date) -> dict:
    """The monthly totals ([{month: 'YYYY-MM', total}], any order) as the server page shows them, in dollars (the AI is billed in
    dollars and is never converted: the rate changes every day): this month, this year, everything there is and since when.
    Pure."""
    shown = sorted(({"month": m["month"], "total": round(float(m["total"]), PRECISION)} for m in months if m["total"]), key=lambda m: m["month"])
    this_month = today.strftime("%Y-%m")
    return {
        "currency": "usd",
        "month": next((m["total"] for m in shown if m["month"] == this_month), 0.0),
        "year": round(sum(m["total"] for m in shown if m["month"][:4] == this_month[:4]), PRECISION),
        "total": round(sum(m["total"] for m in shown), PRECISION),
        "since": shown[0]["month"] if shown else None,
        "months": shown,
    }


def first_day(now: datetime.datetime | None = None) -> int:
    """The start (unix seconds) of the oldest day OpenAI still has: midnight UTC, HISTORY_DAYS ago."""
    today = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(datetime.timezone.utc).date()
    start = datetime.datetime.combine(today - datetime.timedelta(days=HISTORY_DAYS), datetime.time(), tzinfo=datetime.timezone.utc)
    return int(start.timestamp())


def summary(admin_key: str, refresh: bool = False, provider: str = "openai") -> dict:
    """The summary of everything `provider` billed, from memory while it is fresh. Blocks on the network: call it from a worker
    thread. Raises AIError if the provider refuses or does not answer."""
    with _locks[provider]:
        hit = _cached.get(provider)
        if not refresh and hit and hit[0] > time.time():
            return hit[1]
        data = summarize(_COSTS[provider](admin_key, first_day()))
        _cached[provider] = (time.time() + CACHE_SECONDS, data)
        return data


def clear() -> None:
    """Forget what is kept (the tests, and anybody who changes a key)."""
    _cached.clear()

"""Anthropic's Cost API: what the organization has been billed, one bucket per day (UTC), split by what it was spent on.

It takes an **Admin API key** (ANTHROPIC_ADMIN_KEY, `sk-ant-admin01-...`), not the key that writes text, and only an organization of the
Claude Console has one (an individual account must first create its organization). Anthropic has no endpoint for the credit that
is left, only for what was spent. The buckets are returned in the shape of OpenAI's Costs API (`start_time`, `results` with
`amount.value` in dollars and a `line_item`) so that utils/ai_usage.py reads both with the same code.

Written from the documentation (https://platform.claude.com/docs/en/api/beta/organization/cost_report) and tested with answers
made up from it: it has never been run against the real API. What to check on the first real run is VERSION (the header the endpoint
accepts), how far back it answers (utils/ai_usage.HISTORY_DAYS) and the unit of `amount` (cents, as documented)."""
import datetime
from decimal import Decimal

import requests

from .ai_error import AIError

URL = "https://api.anthropic.com/v1/organizations/cost_report"
VERSION = "2023-06-01"  # the version of the Admin API the docs of the legacy endpoints have always shown; newer ones say 2026-10-21
TIMEOUT_SECONDS = 20
PAGE_DAYS = 31  # the most daily buckets a page takes
MAX_PAGES = 40  # about 3 years of days: a stop in case the cursor never ends
USER_AGENT = "LaViciacion/2.0"


def _message(response: requests.Response) -> str:
    try:
        text = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        text = response.reason or ""
    return str(text)[:200]


def _bucket(bucket: dict) -> dict:
    """One daily bucket of Anthropic's report as OpenAI's Costs API gives it. `amount` is a decimal string in cents ("123.45" in USD
    is 1.2345 dollars), `description` says what it was spent on (the model and whether it was input, output, a search...)."""
    start = datetime.datetime.fromisoformat(str(bucket["starting_at"]).replace("Z", "+00:00"))
    return {
        "start_time": int(start.timestamp()),
        "results": [
            {
                "amount": {"value": float(Decimal(str(result.get("amount") or "0")) / 100), "currency": str(result.get("currency") or "USD").lower()},
                "line_item": result.get("description"),
            }
            for result in bucket.get("results") or []
        ],
    }


def costs(admin_key: str, start_time: int) -> list[dict]:
    """The daily buckets since `start_time` (unix seconds), oldest first, in the shape described above. Raises AIError if Anthropic
    refuses or does not answer."""
    starting_at = datetime.datetime.fromtimestamp(start_time, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"x-api-key": admin_key, "anthropic-version": VERSION, "User-Agent": USER_AGENT}
    buckets, page = [], None
    for _ in range(MAX_PAGES):
        params = {"starting_at": starting_at, "bucket_width": "1d", "limit": PAGE_DAYS, "group_by[]": "description"}
        if page:
            params["page"] = page
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as e:
            raise AIError(f"Anthropic no responde ({type(e).__name__})") from None
        if response.status_code in (401, 403):
            raise AIError(f"Anthropic rechaza la clave de administración ({_message(response)})")
        if not response.ok:
            raise AIError(f"Anthropic respondió {response.status_code}: {_message(response)}")
        try:
            body = response.json()
            buckets += [_bucket(b) for b in body.get("data") or []]
        except (ValueError, KeyError, TypeError, ArithmeticError) as e:
            raise AIError(f"Anthropic devolvió un informe de gasto que no se entiende ({type(e).__name__})") from None
        page = body.get("next_page") if body.get("has_more") else None
        if not page:
            return buckets
    raise AIError("Anthropic devolvió demasiadas páginas de gasto")

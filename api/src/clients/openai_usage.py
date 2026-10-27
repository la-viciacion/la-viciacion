"""OpenAI's Costs API: what the organization has been billed, one bucket per day (UTC), split by line item.

It takes an admin key (OPENAI_ADMIN_KEY), not the key that writes text. OpenAI has no endpoint for the credit that is left,
only for what was spent."""
import requests

from .ai_error import AIError

URL = "https://api.openai.com/v1/organization/costs"
TIMEOUT_SECONDS = 20
PAGE_DAYS = 180  # the most days a page takes
MAX_PAGES = 40  # about 20 years of days: a stop in case the cursor never ends


def _message(response: requests.Response) -> str:
    try:
        text = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        text = response.reason or ""
    return str(text)[:200]


def costs(admin_key: str, start_time: int) -> list[dict]:
    """The daily buckets since `start_time` (unix seconds), oldest first. Raises AIError if OpenAI refuses or does not answer."""
    buckets, page = [], None
    for _ in range(MAX_PAGES):
        params = {"start_time": start_time, "bucket_width": "1d", "limit": PAGE_DAYS, "group_by": "line_item"}
        if page:
            params["page"] = page
        try:
            response = requests.get(URL, params=params, headers={"Authorization": f"Bearer {admin_key}"}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as e:
            raise AIError(f"OpenAI no responde ({type(e).__name__})") from None
        if response.status_code in (401, 403):
            raise AIError(f"OpenAI rechaza la clave de administración ({_message(response)})")
        if not response.ok:
            raise AIError(f"OpenAI respondió {response.status_code}: {_message(response)}")
        body = response.json()
        buckets += body.get("data") or []
        page = body.get("next_page") if body.get("has_more") else None
        if not page:
            return buckets
    raise AIError("OpenAI devolvió demasiadas páginas de gasto")

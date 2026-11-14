"""What the account behind a provider's key really holds, for the providers that say so. OpenRouter does (`/credits`, with an ordinary
key): credits bought and used. OpenAI says what was billed (clients/openai_usage.py) but not what is left, and Anthropic and
Google say neither with a key like ours, so their spend is only the app's own estimate."""
from openai import OpenAI

from .model_list import OPENROUTER_URL, TIMEOUT_SECONDS, as_error


def openrouter(key: str) -> dict:
    """Dollars bought, used and left of the OpenRouter account of `key`. Raises QuotaError, ProviderError or AIError (never with the key)."""
    try:
        found = OpenAI(api_key=key, base_url=OPENROUTER_URL, timeout=TIMEOUT_SECONDS, max_retries=0).get("/credits", cast_to=object)["data"]
        credits, used = float(found["total_credits"]), float(found["total_usage"])
    except Exception as e:
        raise as_error("openrouter", key, e) from None
    return {"credits": round(credits, 6), "usage": round(used, 6), "remaining": round(credits - used, 6)}


BALANCES = {"openrouter": openrouter}

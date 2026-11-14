"""The models a key can use, asked to its provider (a call that spends nothing). It is how a key is checked and how the panel offers
a model. It is the one thing pydantic-ai does not do for us, so it has a small function per provider and one way to turn what goes
wrong into the app's errors: QuotaError, ProviderError (its `kind` says a refused key, a timeout...) or AIError, never with the key
in the message."""
import anthropic
from google import genai
from google.genai import types
from openai import OpenAI

from . import failure
from .ai_error import AIError, ProviderError, QuotaError
from .quota import classify

TIMEOUT_SECONDS = 30
OPENROUTER_URL = "https://openrouter.ai/api/v1"


def _openai(key: str) -> list[str]:
    return [m.id for m in OpenAI(api_key=key, timeout=TIMEOUT_SECONDS, max_retries=0).models.list()]


def _openrouter(key: str) -> list[str]:
    """The catalogue of OpenRouter is public, so listing it proves nothing about the key: `/key` is what answers 401 to a wrong one.
    Only the models that write text and can call tools are offered (the chat and the guide need them)."""
    client = OpenAI(api_key=key, base_url=OPENROUTER_URL, timeout=TIMEOUT_SECONDS, max_retries=0)
    client.get("/key", cast_to=object)
    catalogue = client.get("/models", cast_to=object)["data"]
    return [
        m["id"] for m in catalogue
        if (m.get("architecture") or {}).get("output_modalities") == ["text"] and "tools" in (m.get("supported_parameters") or [])
    ]


def _anthropic(key: str) -> list[str]:
    client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_SECONDS, max_retries=0)
    return [m.id for m in client.models.list(limit=1000) if m.id.startswith("claude")]


def _google(key: str) -> list[str]:
    """The Gemini models that write text, without the `models/` prefix."""
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000))  # the SDK counts in milliseconds
    ids = [m.name.removeprefix("models/") for m in client.models.list() if m.name and "generateContent" in (m.supported_actions or [])]
    return [i for i in ids if i.startswith("gemini")]


LISTERS = {"openai": _openai, "google": _google, "anthropic": _anthropic, "openrouter": _openrouter}


def as_error(provider: str, key: str, e: Exception) -> AIError:
    """What a failure of a provider's API is for the app: QuotaError, ProviderError or AIError. A provider's own words may quote the
    key: they never get out."""
    message = f"{provider}: {type(e).__name__}: {str(e).replace(key, '***')}"
    quota = classify(e)
    if quota:
        return QuotaError(message, quota)
    kind = failure.kind(e)
    return ProviderError(message, kind) if kind else AIError(message)


def list_models(provider: str, key: str) -> list[str]:
    """The ids of the models `key` can use at `provider`, sorted."""
    try:
        return sorted(LISTERS[provider](key))
    except Exception as e:
        raise as_error(provider, key, e) from None

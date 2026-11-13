from functools import lru_cache

import anthropic

from . import used
from .ai_error import AIError

TIMEOUT_SECONDS = 30  # the library default is 10 minutes: far too long for a chat notice
MAX_TOKENS = 1024  # Anthropic requires a ceiling on the answer; a notice is a few lines
MAX_TEMPERATURE = 1.0  # Anthropic's scale ends at 1 (OpenAI's at 2): a higher one is refused


@lru_cache(maxsize=2)
def _client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)


def generate(api_key: str, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    message = _client(api_key).messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=min(temperature, MAX_TEMPERATURE),
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    _report(message)
    text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text").strip()
    if not text:
        raise AIError("Anthropic ha respondido sin texto" + (f" ({message.stop_reason})" if message.stop_reason else ""))
    return text


def _report(message) -> None:
    """Leaves the tokens of a message for whoever called (clients/used.py). Anthropic's `input_tokens` leaves out what was read from
    or written to the cache, which the price list counts inside the input: they are added back, the cache reads aside."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    used.report(used.Used(
        input_tokens=(getattr(usage, "input_tokens", 0) or 0) + read + written,
        cached_tokens=read,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    ))


def list_models(api_key: str) -> list[str]:
    """The ids of the Claude models a key can use (a call that spends nothing): it is how a key is checked. The client is not
    cached. Raises QuotaError, ProviderError (its `kind` says a refused key, a timeout...) or AIError, never with the key in the
    message."""
    from . import failure
    from .ai_error import ProviderError, QuotaError
    from .quota import classify

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
        return sorted(model.id for model in client.models.list(limit=1000) if model.id.startswith("claude"))
    except Exception as e:
        message = f"anthropic: {type(e).__name__}: {str(e).replace(api_key, '***')}"
        quota = classify(e)
        if quota:
            raise QuotaError(message, quota) from None
        kind = failure.kind(e)
        raise (ProviderError(message, kind) if kind else AIError(message)) from None

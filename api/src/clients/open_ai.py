from functools import lru_cache

from openai import OpenAI

from .ai_error import AIError

TIMEOUT_SECONDS = 30  # the library default is 10 minutes: far too long for a chat notice


@lru_cache(maxsize=2)
def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS)


def generate(api_key: str, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    completion = _client(api_key).chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
    )
    text = (completion.choices[0].message.content or "").strip() if completion.choices else ""
    if not text:
        raise AIError("OpenAI ha respondido sin texto")
    return text


def list_models(api_key: str) -> list[str]:
    """The ids of the models a key can use (a call that spends nothing): it is how a key is checked. The client is not
    cached, so a player's key is not kept in memory longer than the call. Raises QuotaError, ProviderError (its `kind` says
    a refused key, a timeout...) or AIError, never with the key in the message."""
    from . import failure
    from .ai_error import ProviderError, QuotaError
    from .quota import classify

    try:
        return sorted(model.id for model in OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0).models.list())
    except Exception as e:
        message = f"openai: {type(e).__name__}: {str(e).replace(api_key, '***')}"
        quota = classify(e)
        if quota:
            raise QuotaError(message, quota) from None
        kind = failure.kind(e)
        raise (ProviderError(message, kind) if kind else AIError(message)) from None

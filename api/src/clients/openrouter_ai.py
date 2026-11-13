"""OpenRouter: one key and one balance for many providers' models (a model is named `provider/model`, for example
`anthropic/claude-sonnet-4.5`). Its API is OpenAI's, so the official client is used with OpenRouter's address, and the tokens
are reported as OpenAI's are."""
from functools import lru_cache

from openai import OpenAI

from .ai_error import AIError
from .open_ai import _report

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 30  # a chat notice is not worth a long wait


@lru_cache(maxsize=2)
def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=BASE_URL, timeout=TIMEOUT_SECONDS)


def generate(api_key: str, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    completion = _client(api_key).chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
    )
    _report(completion)
    text = (completion.choices[0].message.content or "").strip() if completion.choices else ""
    if not text:
        raise AIError("OpenRouter ha respondido sin texto")
    return text


def list_models(api_key: str) -> list[str]:
    """The ids of the models OpenRouter offers (a call that spends nothing). The list is public: it does not prove the key, but it
    is what the panel needs to pick a model. The client is not cached. Raises QuotaError, ProviderError or AIError, never with the
    key in the message."""
    from . import failure
    from .ai_error import ProviderError, QuotaError
    from .quota import classify

    try:
        return sorted(model.id for model in OpenAI(api_key=api_key, base_url=BASE_URL, timeout=TIMEOUT_SECONDS, max_retries=0).models.list())
    except Exception as e:
        message = f"openrouter: {type(e).__name__}: {str(e).replace(api_key, '***')}"
        quota = classify(e)
        if quota:
            raise QuotaError(message, quota) from None
        kind = failure.kind(e)
        raise (ProviderError(message, kind) if kind else AIError(message)) from None


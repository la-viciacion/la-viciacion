from functools import lru_cache

from google import genai
from google.genai import errors, types

from . import used
from .ai_error import AIError, QuotaError
from .quota import classify

TIMEOUT_MS = 30_000  # a chat notice is not worth a long wait (the SDK counts in milliseconds)


@lru_cache(maxsize=2)
def _client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def generate(api_key: str, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    try:
        response = _client(api_key).models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=temperature),
        )
    except errors.APIError as e:
        quota = classify(e)
        if quota:
            raise QuotaError(f"Google respondió {e.code}: {quota.describe()}", quota) from None
        raise AIError(f"Google respondió {e.code}: {e.message}") from None
    _report(response)
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None:
        reason = response.prompt_feedback.block_reason if response.prompt_feedback else None
        raise AIError("Google no ha dado ninguna respuesta" + (f" ({reason.name})" if reason else ""))
    text = "".join(part.text or "" for part in (candidate.content.parts if candidate.content else None) or []).strip()
    if not text:
        raise AIError("Google ha respondido sin texto" + (f" ({candidate.finish_reason.name})" if candidate.finish_reason else ""))
    return text


def _report(response) -> None:
    """Leaves the tokens of a response for whoever called (clients/used.py). The thinking of the model is billed as output."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return
    thoughts = getattr(meta, "thoughts_token_count", 0) or 0
    used.report(used.Used(
        input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
        cached_tokens=getattr(meta, "cached_content_token_count", 0) or 0,
        output_tokens=(getattr(meta, "candidates_token_count", 0) or 0) + thoughts,
        reasoning_tokens=thoughts,
    ))


def list_models(api_key: str) -> list[str]:
    """The ids of the Gemini models a key can use to write text (a call that spends nothing), without the `models/` prefix.
    The client is not cached. Raises QuotaError, ProviderError or AIError, never with the key in the message."""
    from . import failure
    from .ai_error import ProviderError

    try:
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        ids = [
            model.name.removeprefix("models/")
            for model in client.models.list()
            if model.name and "generateContent" in (model.supported_actions or [])
        ]
        return sorted(i for i in ids if i.startswith("gemini"))
    except Exception as e:
        message = f"google: {type(e).__name__}: {str(e).replace(api_key, '***')}"
        quota = classify(e)
        if quota:
            raise QuotaError(message, quota) from None
        kind = failure.kind(e)
        raise (ProviderError(message, kind) if kind else AIError(message)) from None

from functools import lru_cache

from google import genai
from google.genai import errors, types

from .ai_error import AIError

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
        raise AIError(f"Google respondió {e.code}: {e.message}") from None
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None:
        reason = response.prompt_feedback.block_reason if response.prompt_feedback else None
        raise AIError("Google no ha dado ninguna respuesta" + (f" ({reason.name})" if reason else ""))
    text = "".join(part.text or "" for part in (candidate.content.parts if candidate.content else None) or []).strip()
    if not text:
        raise AIError("Google ha respondido sin texto" + (f" ({candidate.finish_reason.name})" if candidate.finish_reason else ""))
    return text

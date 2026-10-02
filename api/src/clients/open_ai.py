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

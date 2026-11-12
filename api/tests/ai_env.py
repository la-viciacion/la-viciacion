"""The settings the AI reads (utils/ai_providers.py) as a test double of `settings.get`: one provider with its key and model, the
rest of the providers without a key and no model picked in the panel."""
from src.utils import settings


def group(provider: str | None = "openai", key: str | None = "KEY", model: str | None = "m", chat_model: str | None = None, **overrides) -> dict:
    table = {"ai.provider": provider, "chat.provider": None, "guide.provider": None}
    for p in settings.AI_PROVIDERS:
        table.update({f"ai.{p}.api_key": None, f"ai.{p}.model": None, f"ai.{p}.chat_model": None, f"ai.model.{p}": None, f"chat.model.{p}": None, f"guide.model.{p}": None})
    if provider:
        table.update({f"ai.{provider}.api_key": key, f"ai.{provider}.model": model, f"ai.{provider}.chat_model": chat_model})
    return {**table, **overrides}

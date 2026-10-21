"""The language model the chat talks to. It uses the provider and the key of the notices' AI (AI_PROVIDER, AI_API_KEY),
and its model is the optional CHAT_AI_MODEL (`chat.model`), or AI_MODEL when that is not set: a stronger model for the
chat is the one thing that may differ. Its switch (`chat.enabled`) is its own, apart from the notices'.

Everything is read on every call, so the panel's switch applies at once. pydantic-ai builds the provider's client;
nothing here stores or logs the key."""
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ..utils import settings

# The same provider ids as the notices' (utils/ai.PROVIDERS)
BUILDERS = {
    "openai": lambda name, key: OpenAIChatModel(name, provider=OpenAIProvider(api_key=key)),
    "google": lambda name, key: GoogleModel(name, provider=GoogleProvider(api_key=key)),
}


def model_name() -> str | None:
    """The chat's own model if there is one, else the notices' AI model."""
    return settings.get("chat.model") or settings.get("ai.model")


def configured() -> bool:
    """There is a known provider, a key and a model in the environment (whether the chat is switched on or not)."""
    return bool(settings.get("ai.api_key") and settings.get("ai.provider") in BUILDERS and model_name())


def is_ready() -> bool:
    """The chat is switched on and configured: what the players see."""
    return bool(settings.get("chat.enabled") and configured())


def in_use() -> dict:
    """For the panel: the provider and the model (None if missing) the chat will use, and whether the model is its own."""
    return {"provider": settings.get("ai.provider"), "model": model_name(), "own_model": bool(settings.get("chat.model"))}


def build_model() -> Model:
    return BUILDERS[settings.get("ai.provider")](model_name(), settings.get("ai.api_key"))

"""The language model the chat talks to, built from the same settings as the notices (utils/ai.py).

Provider, model and key are read on every call, so the panel's switch and the .env changes apply without a
restart. pydantic-ai builds the provider's client; nothing here stores or logs the key."""
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ..utils import settings

# The same provider ids as utils/ai.PROVIDERS
BUILDERS = {
    "openai": lambda name, key: OpenAIChatModel(name, provider=OpenAIProvider(api_key=key)),
    "google": lambda name, key: GoogleModel(name, provider=GoogleProvider(api_key=key)),
}


def is_ready() -> bool:
    """The AI is on for the chat and has a known provider, a model and a key."""
    return bool(
        settings.get("ai.enabled")
        and settings.get("ai.use.chat")
        and settings.get("ai.api_key")
        and settings.get("ai.provider") in BUILDERS
        and settings.get("ai.model")
    )


def build_model() -> Model:
    return BUILDERS[settings.get("ai.provider")](settings.get("ai.model"), settings.get("ai.api_key"))

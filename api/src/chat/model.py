"""The language model the chat talks to. It uses the provider chosen for the AI and its key (utils/ai_providers.py), and its
model is the chat's own (picked in the panel, or <PROVIDER>_CHAT_AI_MODEL), or the notices' when there is none: a stronger
model for the chat is the one thing that may differ. Its switch (`chat.enabled`) is its own, apart from the notices'.

Everything is read on every call, so the panel's switch applies at once. pydantic-ai builds the provider's client;
nothing here stores or logs the key."""
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from ..utils import ai_providers, settings

# The same provider ids as the notices' (utils/ai.PROVIDERS)
BUILDERS = {
    "openai": lambda name, key: OpenAIChatModel(name, provider=OpenAIProvider(api_key=key)),
    "google": lambda name, key: GoogleModel(name, provider=GoogleProvider(api_key=key)),
    "anthropic": lambda name, key: AnthropicModel(name, provider=AnthropicProvider(api_key=key)),
    "openrouter": lambda name, key: OpenRouterModel(name, provider=OpenRouterProvider(api_key=key)),
}


def model_name() -> str | None:
    """The chat's own model if there is one, else the notices' AI model."""
    return ai_providers.model(ai_providers.CHAT)


def configured() -> bool:
    """There is a provider with a key and a model (whether the chat is switched on or not)."""
    return ai_providers.group_credentials(ai_providers.CHAT) is not None


def is_ready() -> bool:
    """The chat is switched on and configured: what the players see."""
    return bool(settings.get("chat.enabled") and configured())


def in_use() -> dict:
    """For the panel: the provider and the model (None if missing) the chat will use, and whether the model is its own."""
    return ai_providers.in_use(ai_providers.CHAT)


def build_model(source=None) -> Model:
    """The model for a source of key (utils/ai_source.py): the player's own, or the group's when there is none."""
    if source is not None:
        return BUILDERS[source.provider](source.model, source.api_key)
    provider, key, name = ai_providers.group_credentials(ai_providers.CHAT)
    return BUILDERS[provider](name, key)

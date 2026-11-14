"""The language model of a provider, for pydantic-ai: the one place that knows how to build each of them.

Everything the app asks a model for (the notices, the chat and the guide) goes through pydantic-ai, so a new provider is one line in
`_CLASSES` (and the key and model variables of utils/settings.py), not a client of its own."""
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from . import ai_providers

# provider id (utils/settings.py AI_PROVIDERS) -> the model class and the provider class that hold its key
_CLASSES = {
    "openai": (OpenAIChatModel, OpenAIProvider),
    "google": (GoogleModel, GoogleProvider),
    "anthropic": (AnthropicModel, AnthropicProvider),
    "openrouter": (OpenRouterModel, OpenRouterProvider),
}


def build(provider: str, name: str, key: str, *, web_search: bool = False) -> Model:
    """The model `name` of `provider`, with `key`. `web_search` asks for one that can use the provider's own web search (the
    guide): OpenAI's is only in its Responses API, the others' models have it."""
    model_class, provider_class = _CLASSES[provider]
    if web_search and provider == "openai":
        model_class = OpenAIResponsesModel
    return model_class(name, provider=provider_class(api_key=key))


def model_for(use: str, source=None) -> Model:
    """The model that answers `use` (ai_providers.CHAT, GUIDE...) with a source of key (utils/ai_source.py): the player's own, or
    the group's, with the provider and model the admin chose for that use, when none is given."""
    if source is not None:
        provider, key, name = source.provider, source.api_key, source.model
    else:
        provider, key, name = ai_providers.group_credentials(use)
    return build(provider, name, key, web_search=use == ai_providers.GUIDE)

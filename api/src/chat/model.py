"""The language model the chat talks to. It uses the provider chosen for the AI and its key (utils/ai_providers.py), and its
model is the chat's own (picked in the panel, or <PROVIDER>_CHAT_AI_MODEL), or the notices' when there is none: a stronger
model for the chat is the one thing that may differ. Its switch (`chat.enabled`) is its own, apart from the notices'.

Everything is read on every call, so the panel's switch applies at once. The model itself is built by utils/ai_build.py."""
from ..utils import ai_providers, settings


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

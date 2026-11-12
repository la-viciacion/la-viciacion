"""Which AI provider and which model the group's key uses.

Every provider has its own variables in the .env (OPENAI_AI_API_KEY, OPENAI_AI_MODEL, OPENAI_CHAT_AI_MODEL, GOOGLE_...): a
provider exists for the app when its key is set. There is no variable that says which one to use. When several have a key,
the admin picks one in the panel (`ai.provider`, stored) and, per provider, the model of the notices (`ai.model.<provider>`)
and the one of the chat and the guide (`chat.model.<provider>`); the .env's model is the default while nobody picks another.
A pick that no longer fits (its provider lost its key) is ignored: the first provider that has one is used.

Read on every call, so a change in the panel applies at once."""
from . import settings

PROVIDERS = settings.AI_PROVIDERS
NOTICES, CHAT = "notices", "chat"  # what a model is for: the notices, or the chat and the guide


def api_key(provider: str | None) -> str | None:
    return settings.get(f"ai.{provider}.api_key") if provider in PROVIDERS else None


def available() -> list[str]:
    """The providers with a key in the environment, in the order of PROVIDERS."""
    return [p for p in PROVIDERS if api_key(p)]


def selected() -> str | None:
    """The provider in use: the admin's pick if it still has a key, else the first that has one, else None."""
    ready = available()
    picked = settings.get("ai.provider")
    return picked if picked in ready else (ready[0] if ready else None)


def default_model(provider: str, use: str = NOTICES) -> str | None:
    """The model of the environment for a provider (the chat's own if it has one, else the notices')."""
    notices = settings.get(f"ai.{provider}.model")
    return (settings.get(f"ai.{provider}.chat_model") or notices) if use == CHAT else notices


def model(use: str = NOTICES, provider: str | None = None) -> str | None:
    """The model a provider (the selected one by default) uses for `use`: the admin's pick, else the environment's default.
    The chat falls back to the model of the notices (the pick included) when it has neither."""
    provider = provider or selected()
    if provider not in PROVIDERS:
        return None
    if use == CHAT:
        return settings.get(f"chat.model.{provider}") or settings.get(f"ai.{provider}.chat_model") or model(NOTICES, provider)
    return settings.get(f"ai.model.{provider}") or settings.get(f"ai.{provider}.model")


def own_model(use: str, provider: str) -> bool:
    """The admin has picked a model for this provider and use (it is not the environment's default)."""
    return bool(settings.get(f"{'chat' if use == CHAT else 'ai'}.model.{provider}"))


def current(use: str = NOTICES) -> tuple[str | None, str | None]:
    """(provider, model) in use, None where missing: the code has no default for either."""
    provider = selected()
    return provider, model(use, provider)


def group_credentials(use: str = NOTICES) -> tuple[str, str, str] | None:
    """(provider, key, model) of the group's key, or None when there is no provider with a key and a model."""
    provider, name = current(use)
    key = api_key(provider)
    return (provider, key, name) if provider and key and name else None


def status() -> dict:
    """For the panel: what the environment has (the providers with a key and their default models) and what is in use now."""
    return {
        "providers": [
            {"id": p, "has_key": bool(api_key(p)), "default_model": default_model(p, NOTICES), "default_chat_model": default_model(p, CHAT)}
            for p in PROVIDERS
        ],
        "provider": selected(),
        "picked": settings.get("ai.provider"),
        "notices_model": model(NOTICES),
        "chat_model": model(CHAT),
        "notices_own": bool(selected()) and own_model(NOTICES, selected()),
        "chat_own": bool(selected()) and own_model(CHAT, selected()),
    }

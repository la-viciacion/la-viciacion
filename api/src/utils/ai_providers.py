"""Which AI provider and which model the group's key uses, for each of the three things the AI does: the notices, the chat and the
game guide.

Every provider has its own variables in the .env (OPENAI_AI_API_KEY, OPENAI_AI_MODEL, OPENAI_CHAT_AI_MODEL, GOOGLE_...): a
provider exists for the app when its key is set. There is no variable that says which one to use. When several have a key,
the admin picks one for each use in the panel (`ai.provider`, `chat.provider`, `guide.provider`, stored) and, per provider, a
model for each (`ai.model.<provider>`, `chat.model.<provider>`, `guide.model.<provider>`). Without a pick the chat follows the
notices' provider and the guide follows the chat's, and the notices take the first provider that has a key and a model; a model
falls back the same way, ending in the .env's default. A pick that no longer fits (its provider lost its key) is ignored.

Read on every call, so a change in the panel applies at once."""
from . import settings

PROVIDERS = settings.AI_PROVIDERS
NOTICES, CHAT, GUIDE = "notices", "chat", "guide"  # what a model is for
USES = (NOTICES, CHAT, GUIDE)
_PREFIX = {NOTICES: "ai", CHAT: "chat", GUIDE: "guide"}  # the settings of each use: `<prefix>.provider`, `<prefix>.model.<provider>`
_FALLBACK = {CHAT: NOTICES, GUIDE: CHAT}  # who a use follows when nothing is picked for it


def api_key(provider: str | None) -> str | None:
    return settings.get(f"ai.{provider}.api_key") if provider in PROVIDERS else None


def available() -> list[str]:
    """The providers with a key in the environment, in the order of PROVIDERS."""
    return [p for p in PROVIDERS if api_key(p)]


def selected(use: str = NOTICES) -> str | None:
    """The provider a use runs on: the admin's pick for it if it still has a key (even if it has no model: the panel says what is
    missing), else the one it follows (the guide follows the chat, the chat the notices), else the first that has a key **and a
    model**, else the first with a key, else None. A provider with a key and no model must not hide one that is complete."""
    ready = available()
    picked = settings.get(f"{_PREFIX[use]}.provider")
    if picked in ready:
        return picked
    if use in _FALLBACK:
        return selected(_FALLBACK[use])
    return next((p for p in ready if model(use, p)), ready[0] if ready else None)


def default_model(provider: str, use: str = NOTICES) -> str | None:
    """The model of the environment for a provider (the chat's own if it has one, else the notices'); the guide's is the chat's."""
    notices = settings.get(f"ai.{provider}.model")
    return notices if use == NOTICES else (settings.get(f"ai.{provider}.chat_model") or notices)


def model(use: str = NOTICES, provider: str | None = None) -> str | None:
    """The model a provider (the one selected for `use` by default) uses for `use`: the admin's pick for it, else what the use
    follows (the guide the chat's, the chat the notices'), else the environment's default."""
    provider = provider or selected(use)
    if provider not in PROVIDERS:
        return None
    picked = settings.get(f"{_PREFIX[use]}.model.{provider}")
    if picked:
        return picked
    if use == NOTICES:
        return settings.get(f"ai.{provider}.model")
    if use == CHAT and settings.get(f"ai.{provider}.chat_model"):
        return settings.get(f"ai.{provider}.chat_model")
    return model(_FALLBACK[use], provider)


def own_model(use: str, provider: str) -> bool:
    """The admin has picked a model for this provider and use (it is not the one the use follows)."""
    return bool(settings.get(f"{_PREFIX[use]}.model.{provider}"))


def current(use: str = NOTICES) -> tuple[str | None, str | None]:
    """(provider, model) in use for `use`, None where missing: the code has no default for either."""
    provider = selected(use)
    return provider, model(use, provider)


def group_credentials(use: str = NOTICES) -> tuple[str, str, str] | None:
    """(provider, key, model) of the group's key for `use`, or None when there is no provider with a key and a model."""
    provider, name = current(use)
    key = api_key(provider)
    return (provider, key, name) if provider and key and name else None


def model_problem(provider: str | None, name: str | None) -> str | None:
    """Why a model cannot work with its provider, in Spanish for the panel, or None. OpenRouter wants `vendor/model`; without the
    vendor every call fails when its model is built, and the .env's value is not checked by anything else."""
    if provider == "openrouter" and name and "/" not in name:
        return f"OpenRouter nombra los modelos «proveedor/modelo» (por ejemplo openai/{name}), no «{name}»"
    return None


def in_use(use: str) -> dict:
    """What a use runs on now: the provider and the model (None if missing), whether the model was picked in the panel and, if it
    cannot work, why (`problem`)."""
    provider, name = current(use)
    return {"provider": provider, "model": name, "own_model": bool(provider) and own_model(use, provider), "problem": model_problem(provider, name)}


def status() -> dict:
    """For the panel: what the environment has (the providers with a key and their default models) and what each use runs on."""
    return {
        "providers": [
            {"id": p, "has_key": bool(api_key(p)), "default_model": default_model(p, NOTICES), "default_chat_model": default_model(p, CHAT)}
            for p in PROVIDERS
        ],
        "uses": {use: {**in_use(use), "picked": settings.get(f"{_PREFIX[use]}.provider")} for use in USES},
    }

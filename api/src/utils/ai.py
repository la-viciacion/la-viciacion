"""AI-written text for the notices: one entry point for every provider.

What is used (switch, provider, key, model) is read from the settings on every call
(utils/settings.py), so the admin panel changes it without restarting anything. The
functions block on the network: call them from a worker thread.
"""
from ..clients import google_ai, open_ai
from ..clients.ai_error import AIError
from . import settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

PROVIDERS = {"google": google_ai.generate, "openai": open_ai.generate}

__all__ = ["AIError", "complete", "current", "is_ready", "prompt_for"]


def is_ready(use: str | None = None) -> bool:
    """Switched on, with a key, a known provider and a model; with `use` (a switchable id of ai_prompts.USES), also on
    for that notice."""
    return bool(
        settings.get("ai.enabled")
        and settings.get("ai.api_key")
        and settings.get("ai.provider") in PROVIDERS
        and settings.get("ai.model")
        and (use is None or settings.get(f"ai.use.{use}"))
    )


def prompt_for(use: str, recommended: dict | None = None) -> str:
    """The instructions for a notice: the admin's prompt if there is one, the code's otherwise.
    `recommended` ({"game", "reasons"}) adds the suggestion of another game and why it was picked (never who has it)."""
    text = settings.get(f"ai.prompt.{use}")
    if recommended:
        text += "\n" + settings.get("ai.prompt.completed_game_recommendation") + "\n"
        text += f"Juego recomendado: {recommended['game']}"
        if recommended.get("reasons"):
            text += "\nMotivos:" + "".join(f"\n- {reason}" for reason in recommended["reasons"])
    return text


def current() -> tuple[str | None, str | None]:
    """(provider, model) in use. They come only from AI_PROVIDER and AI_MODEL (None if missing): the code has no default."""
    return settings.get("ai.provider"), settings.get("ai.model")


def in_use() -> dict:
    """For the panel: the provider and the model (None if AI_PROVIDER or AI_MODEL is missing) the notices will use now."""
    provider, model = current()
    return {"provider": provider, "model": model}


def complete(system_prompt: str, user_prompt: str, *, temperature: float = 1.0, force: bool = False) -> str | None:
    """The text the AI writes, or None when the AI is off or has no key (`force` ignores the switch,
    for the test button). Raises AIError if the provider fails."""
    key = settings.get("ai.api_key")
    provider, model = current()
    if not key or provider not in PROVIDERS or not model or not (force or settings.get("ai.enabled")):
        return None
    try:
        return PROVIDERS[provider](key, model, system_prompt, user_prompt, temperature)
    except AIError:
        raise
    except Exception as e:
        # a provider library may quote what it was given: never let the key out in the message
        raise AIError(f"{provider}: {type(e).__name__}: {str(e).replace(key, '***')}") from None

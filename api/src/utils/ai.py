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
DEFAULT_MODELS = {"google": "gemini-2.5-flash", "openai": "gpt-4o-mini"}

__all__ = ["AIError", "complete", "current", "is_ready", "prompt_for"]


def is_ready(use: str | None = None) -> bool:
    """Switched on and with a key; with `use` (a switchable id of ai_prompts.USES), also on for that notice."""
    return bool(
        settings.get("ai.enabled") and settings.get("ai.api_key") and (use is None or settings.get(f"ai.use.{use}"))
    )


def prompt_for(use: str, recommended: dict | None = None) -> str:
    """The instructions for a notice: the admin's prompt if there is one, the code's otherwise.
    `recommended` ({"game", "user"}) adds the suggestion of another game."""
    text = settings.get(f"ai.prompt.{use}")
    if recommended:
        text += "\n" + settings.get("ai.prompt.completed_game_recommendation") + "\n"
        text += f"Juego recomendado: {recommended['game']}\nJugado por: {recommended['user']}"
    return text


def current() -> tuple[str, str]:
    """(provider, model) in use; the model falls back to the provider's default."""
    provider = settings.get("ai.provider")
    return provider, settings.get("ai.model") or DEFAULT_MODELS[provider]


def complete(system_prompt: str, user_prompt: str, *, temperature: float = 1.0, force: bool = False) -> str | None:
    """The text the AI writes, or None when the AI is off or has no key (`force` ignores the switch,
    for the test button). Raises AIError if the provider fails."""
    key = settings.get("ai.api_key")
    if not key or not (force or settings.get("ai.enabled")):
        return None
    provider, model = current()
    try:
        return PROVIDERS[provider](key, model, system_prompt, user_prompt, temperature)
    except AIError:
        raise
    except Exception as e:
        # a provider library may quote what it was given: never let the key out in the message
        raise AIError(f"{provider}: {type(e).__name__}: {str(e).replace(key, '***')}") from None

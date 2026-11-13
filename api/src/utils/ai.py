"""AI-written text for the notices: one entry point for every provider.

What is used (switch, provider, key, model) is read from the settings on every call
(utils/settings.py), so the admin panel changes it without restarting anything. The
functions block on the network: call them from a worker thread.
"""
import time

from ..clients import anthropic_ai, google_ai, open_ai, used
from ..clients.ai_error import AIError, QuotaError
from ..clients.quota import classify
from . import ai_ledger, ai_providers, ai_quota, settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

PROVIDERS = {"google": google_ai.generate, "openai": open_ai.generate, "anthropic": anthropic_ai.generate}

__all__ = ["AIError", "QuotaError", "complete", "current", "is_ready", "prompt_for"]


def is_ready(use: str | None = None) -> bool:
    """Switched on, with a provider that has a key and a model; with `use` (a switchable id of ai_prompts.USES), also on
    for that notice."""
    return bool(
        settings.get("ai.enabled")
        and ai_providers.group_credentials()
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
    """(provider, model) in use for the notices (None if missing): see utils/ai_providers.py."""
    return ai_providers.current()


def in_use() -> dict:
    """For the panel: the provider and the model (None if no provider has a key and a model) the notices will use now."""
    provider, model = current()
    return {"provider": provider, "model": model}


def complete(system_prompt: str, user_prompt: str, *, temperature: float = 1.0, force: bool = False, source: str = "notice") -> str | None:
    """The text the AI writes, or None when the AI is off or has no key (`force` ignores the switch,
    for the test button). Raises AIError if the provider fails, QuotaError (an AIError) if a quota ran out: that one is
    also written to the audit log (utils/ai_quota.py), `source` saying who asked."""
    found = ai_providers.group_credentials()
    if found is None or not (force or settings.get("ai.enabled")):
        return None
    provider, key, model = found
    started = time.monotonic()
    used.discard()
    try:
        text = PROVIDERS[provider](key, model, system_prompt, user_prompt, temperature)
        ai_ledger.record_notice(source, provider, model, ai_ledger.OK, started, used.take())
        return text
    except QuotaError as e:
        ai_quota.report(e.quota, source, provider, model)
        ai_ledger.record_notice(source, provider, model, ai_ledger.QUOTA, started)
        raise
    except AIError:
        ai_ledger.record_notice(source, provider, model, ai_ledger.ERROR, started)
        raise
    except Exception as e:
        quota = classify(e)
        if quota:
            ai_quota.report(quota, source, provider, model)
            ai_ledger.record_notice(source, provider, model, ai_ledger.QUOTA, started)
            raise QuotaError(f"{provider}: {quota.describe()}", quota) from None
        ai_ledger.record_notice(source, provider, model, ai_ledger.ERROR, started)
        # a provider library may quote what it was given: never let the key out in the message
        raise AIError(f"{provider}: {type(e).__name__}: {str(e).replace(key, '***')}") from None

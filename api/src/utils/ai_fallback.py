"""What happens when the call that a key pays for fails: whether the next key is tried and what the player is told.

A question has an ordered list of keys that may pay for it (`ai_source.Decision.sources`: the group's first and then the player's own
ones, when the mode lets them, or only their own). The first is called. Money decides what happens when it fails:

  * only a failure **of the key itself** moves on to the next one: the account has no balance left or its daily quota is gone
    (`QuotaError` of kind `billing` or `day`), or the provider refuses the key (`DENIED`). Those are states that last, in which that key
    cannot answer, so the next one, which the player allowed by saving it, takes over;
  * a rate limit (a per-minute quota, or a 429 that does not say) passes in seconds, like a timeout, an overload or a server error: it
    does not move on, and the player is told to wait. Moving on would bill their account for a throttle of the group's key. Neither does
    that failure of the provider: it usually passes in seconds, and trying again
    on the player's account for a hiccup of the group's provider would spend their money for nothing. The player is told to retry;
  * a failure with nothing to tell (a 400, a model that does not exist) is a configuration problem, not a key that cannot pay: it does not
    move on either.

At most `ai_source.MAX_OWN_KEYS` of the player's own keys are tried after the group's, and each key is called once per question. Every
attempt leaves its own row in the usage record (the agents write it), with the key that was used, so what the group's key refused and
what the player's paid in its place can both be read there; the group's quota refusals also reach the audit log (utils/ai_quota.py).

`explain` turns what happened into the answer of the API: it says **which** key failed and **why**, for every attempt, so nothing is lost
when two fail, and it never names a key or quotes the provider's text."""
from dataclasses import dataclass

from fastapi import HTTPException

from ..clients import failure
from ..clients.ai_error import AIError, QuotaError, wait_text
from . import messages
from .logger import LogManager

logger = LogManager().get_logger()

NAMES = {"openai": "OpenAI", "google": "Google", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
# Where a player tops up the account of their own key
BILLING = {
    "openai": "platform.openai.com → Billing", "anthropic": "platform.claude.com → Billing",
    "google": "aistudio.google.com → Billing", "openrouter": "openrouter.ai/credits",
}
GROUP_MESSAGES = {
    failure.TIMEOUT: messages.CHAT_TIMEOUT,
    failure.OVERLOADED: messages.CHAT_OVERLOADED,
    failure.SERVER: messages.CHAT_SERVER,
    failure.DENIED: messages.CHAT_DENIED,
}


@dataclass(frozen=True)
class Attempt:
    source: object  # ai_source.Source
    error: AIError


class Failed(AIError):
    """Every key that was tried failed: `attempts` says each one, in the order they were called."""

    def __init__(self, attempts: list[Attempt]):
        super().__init__("; ".join(str(a.error) for a in attempts))
        self.attempts = attempts


def kind_of(error: AIError) -> str | None:
    return getattr(error, "kind", None)


LASTING_QUOTAS = ("billing", "day")  # Quota.kind of a quota that does not come back in seconds


def worth_next(error: AIError) -> bool:
    """Whether this failure means the key cannot pay for a while (its balance or daily quota is gone, or the provider refuses it), so
    the next key may be tried. A rate limit, a transient failure or one without a reason is not: see the module's text."""
    if isinstance(error, QuotaError):
        return error.quota.kind in LASTING_QUOTAS
    return kind_of(error) == failure.DENIED


def run(sources, call, feature: str):
    """Calls `call(source)` with each source in turn until one answers, and returns its result. It moves on only after a failure of
    the key (`worth_next`) and only while there is a next one; otherwise it raises `Failed` with every attempt. `call` raises an
    AIError when the provider fails (after leaving its row in the usage record)."""
    attempts: list[Attempt] = []
    for index, source in enumerate(sources):
        try:
            result = call(source)
        except AIError as error:
            attempts.append(Attempt(source, error))
            _log(feature, source, error)
            if not worth_next(error) or index == len(sources) - 1:
                raise Failed(attempts) from None
            continue
        if attempts:
            first = attempts[0]
            logger.info(
                f"{feature.capitalize()} answered with a {source.key_source} {source.provider} key after the {first.source.key_source} "
                f"{first.source.provider} one failed ({_what(first.error)})"
            )
        return result
    raise ValueError("a question needs at least one key")


def _what(error: AIError) -> str:
    if isinstance(error, QuotaError):
        return f"quota {error.quota.kind}"
    return kind_of(error) or "error"


def _log(feature: str, source, error: AIError) -> None:
    """Writes what failed. The group's key being refused or broken is for the admins whether or not the player's own key then answered
    (an error: Sentry); a quota is already in the audit log and a slow provider is not a bug of ours (a warning); a player's own key that
    fails is theirs to fix (a warning), unless it is a failure with nothing to tell."""
    text = f"{feature.capitalize()} failed with a {source.key_source} {source.provider} key: {error}"
    kind = kind_of(error)
    if isinstance(error, QuotaError) or kind in (failure.TIMEOUT, failure.OVERLOADED):
        logger.warning(text)
    elif source.own:
        (logger.warning if kind else logger.error)(text, exc_info=not kind)
    else:
        logger.error(text, exc_info=kind != failure.DENIED)


# ── what the player is told ─────────────────────────────────────────────────────────────────────
def _when(error: AIError) -> str:
    retry = error.quota.retry_after if isinstance(error, QuotaError) else None
    return f" (reintenta en {wait_text(retry)})" if retry else ""


def _group_reason(error: AIError) -> str:
    if isinstance(error, QuotaError):
        return "se ha quedado sin saldo" if error.quota.kind == "billing" else f"ha llegado a su límite de uso{_when(error)}"
    return {
        failure.DENIED: "no es aceptada por el proveedor",
        failure.TIMEOUT: "ha tardado demasiado",
        failure.OVERLOADED: "no puede atender ahora mismo",
        failure.SERVER: "ha tenido un fallo",
    }.get(kind_of(error), "ha fallado")


def _own_reason(provider: str, error: AIError) -> str:
    name = NAMES.get(provider, provider)
    if isinstance(error, QuotaError):
        if error.quota.kind == "billing":
            return f"se ha quedado sin saldo (revisa tu cuenta en {BILLING.get(provider, name)})"
        return f"ha llegado a su límite de uso{_when(error)}"
    return {
        failure.DENIED: f"no es aceptada por {name} (¿la has borrado o revocado? Vuelve a guardarla en Ajustes → Mi IA)",
        failure.TIMEOUT: f"no ha respondido a tiempo ({name} tarda demasiado): inténtalo otra vez",
        failure.OVERLOADED: f"no ha podido responder porque {name} está saturado: prueba en un rato",
        failure.SERVER: f"no ha podido responder porque {name} ha tenido un fallo: inténtalo otra vez",
    }.get(kind_of(error), f"ha fallado y {name} no dice por qué: inténtalo en un rato")


def own_problem(provider: str, error: AIError) -> str:
    """One sentence about a failure of a player's own key (for the routes that test or save it)."""
    return f"Tu clave de {NAMES.get(provider, provider)} {_own_reason(provider, error)}"


def _sentence(attempt: Attempt) -> str:
    source = attempt.source
    if source.own:
        return f"tu clave de {NAMES.get(source.provider, source.provider)} {_own_reason(source.provider, attempt.error)}"
    return f"la clave del grupo {_group_reason(attempt.error)}"


def explain(attempts: list[Attempt], way_out=lambda: "") -> HTTPException:
    """The answer for a question that no key could pay. One key failed: the group's gets the usual texts (plus `way_out()`, how the player
    can go on with their own key, only when the group's quota or key was the problem and there was nothing to fall back on); a
    player's own is told it is theirs and why. More than one failed: all of them are named, each with its reason. The status is 504 for
    a timeout, 429 for a quota and 502 for the rest, never 503 (the front reads that as the feature being switched off)."""
    last = attempts[-1]
    error = last.error
    kind = kind_of(error)
    headers = None
    if isinstance(error, QuotaError) and error.quota.retry_after:
        headers = {"Retry-After": str(error.quota.retry_after)}
    status = 429 if isinstance(error, QuotaError) else 504 if kind == failure.TIMEOUT else 502
    if len(attempts) > 1:
        detail = "No he podido responder: " + "; ".join(_sentence(a) for a in attempts) + "."
    elif last.source.own:
        detail = own_problem(last.source.provider, error) + "."
    elif isinstance(error, QuotaError):
        detail = messages.CHAT_QUOTA.format(when=_when(error)) + (way_out() if worth_next(error) else "")
    else:
        detail = GROUP_MESSAGES.get(kind, messages.CHAT_FAILED) + (way_out() if worth_next(error) else "")
    return HTTPException(status_code=status, detail=detail, headers=headers)

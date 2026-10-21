"""How a provider failed, when it is a way a player can be told about (the quota has its own: clients/quota.py).

The answer to a player is a joke about the free tier and says what happened in one word: the provider took too long, it is
overloaded, it had a bad day, or it refused our key or project. Anything else is a failure with nothing to tell, which the
caller words as a plain "it could not answer". Read from the HTTP status, whichever library raised it."""
from pydantic_ai.exceptions import ModelRequestTimeout, ModelTimeoutError

from .quota import chain, status_and_body

TIMEOUT, OVERLOADED, SERVER, DENIED = "timeout", "overloaded", "server", "denied"
TIMEOUTS = (ModelTimeoutError, ModelRequestTimeout, TimeoutError)


def kind(exc: BaseException) -> str | None:
    """"timeout", "overloaded", "server", "denied", or None for anything else."""
    for found in chain(exc):
        if isinstance(found, TIMEOUTS):
            return TIMEOUT
        status, _, _ = status_and_body(found)
        if status in (408, 504):
            return TIMEOUT
        if status in (503, 529):
            return OVERLOADED
        if status in (401, 403):
            return DENIED
        if status is not None and status >= 500:
            return SERVER
    return None

"""What the last completion of a provider used, so a client that returns only a text can still say what it cost.

The clients of the notices (open_ai.generate, google_ai.generate) return the text and, on the side, leave the tokens here for the
thread that called them; `ai.complete` takes them right after the call to write the record of usage (utils/ai_ledger.py). A
thread-local keeps two notices written at once from reading each other's numbers, and the signature of the clients (and every
test that mocks them) stays as it was."""
import threading
from dataclasses import dataclass

_local = threading.local()


@dataclass(frozen=True)
class Used:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0  # the model's thinking included: it is billed as output
    reasoning_tokens: int = 0


def report(used: Used) -> None:
    _local.used = used


def take() -> Used | None:
    """The tokens the last call of this thread used (once), or None if it left none."""
    used = getattr(_local, "used", None)
    _local.used = None
    return used


def discard() -> None:
    _local.used = None

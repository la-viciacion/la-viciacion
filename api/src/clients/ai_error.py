from dataclasses import dataclass


class AIError(Exception):
    """The AI provider did not give a text; the message says why (never contains the key)."""


@dataclass(frozen=True)
class Quota:
    """What a provider said when it refused a call for lack of quota (HTTP 429)."""

    kind: str = "unknown"  # "minute" | "day" | "billing" | "unknown": the period of the quota that ran out, when it says
    retry_after: int | None = None  # seconds the provider asks to wait
    ids: tuple[str, ...] = ()  # the quotas that ran out, as the provider names them
    limit: str | None = None  # the figure of the quota, as the provider gives it
    message: str = ""  # the provider's own text, cut

    def describe(self) -> str:
        """For a person (Spanish): which quota ran out and when to try again."""
        period = {"minute": " por minuto", "day": " por día", "billing": " de facturación"}.get(self.kind, "")
        what = f"Cupo de la IA agotado{period}"
        if self.ids:
            what += f" ({', '.join(self.ids)}{f', límite {self.limit}' if self.limit else ''})"
        return what + (f". Reintenta en {wait_text(self.retry_after)}" if self.retry_after else "")


def wait_text(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    return f"{round(seconds / 3600)} h"


class ProviderError(AIError):
    """The provider failed in a way a player can be told about: `kind` is one of clients/failure.py."""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


class QuotaError(AIError):
    """The provider refused the call because a quota ran out (a per-minute limit, the day's, or the billing)."""

    def __init__(self, message: str, quota: Quota):
        super().__init__(message)
        self.quota = quota

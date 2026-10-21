"""Recognizes a provider's "out of quota" answer (HTTP 429), whichever library raised it.

Google answers 429 RESOURCE_EXHAUSTED with a QuotaFailure (which quota ran out, and its limit) and a RetryInfo (how long
to wait); OpenAI answers 429 with a code (`insufficient_quota` when the billing ran out, `rate_limit_exceeded` for a
rate) and a `retry-after` header. pydantic-ai wraps both in a ModelHTTPError. Everything is read defensively: a
provider changing its answer must degrade to "a quota ran out" with less detail, never to an exception."""
import math
import re

import openai
from google.genai import errors as google_errors
from pydantic_ai.exceptions import ModelHTTPError

from .ai_error import Quota

MESSAGE_MAX = 300
CHAIN_MAX = 5  # how many exceptions of a `raise ... from` chain are looked at


def _chain(exc: BaseException):
    seen = 0
    while exc is not None and seen < CHAIN_MAX:
        yield exc
        exc = exc.__cause__ or exc.__context__
        seen += 1


def _status_and_body(exc: BaseException) -> tuple[int | None, object, dict]:
    """(HTTP status, parsed body, headers) of an exception of a library we know; (None, None, {}) of any other."""
    if isinstance(exc, google_errors.APIError):
        response = getattr(exc, "response", None)
        return exc.code, exc.details, dict(getattr(response, "headers", None) or {})
    if isinstance(exc, ModelHTTPError):
        return exc.status_code, exc.body, dict(exc.headers or {})
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code, exc.body, dict(getattr(exc.response, "headers", None) or {})
    return None, None, {}


def _seconds(text) -> int | None:
    """"34s", "34.5s", "2m", "120" -> whole seconds (rounded up)."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*", str(text or ""))
    if not match:
        return None
    unit = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, None: 1}[match.group(2)]
    return math.ceil(float(match.group(1)) * unit)


def _kind(ids: tuple[str, ...], code) -> str:
    text = " ".join(ids).lower()
    if "perday" in text or "per_day" in text:
        return "day"
    if "perminute" in text or "per_minute" in text:
        return "minute"
    if str(code).lower() == "insufficient_quota":
        return "billing"
    return "unknown"


def _quota(body: object, headers: dict, retry_after: float | None = None) -> Quota:
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body
    error = error if isinstance(error, dict) else {}
    ids: list[str] = []
    limit = None
    retry = _seconds(headers.get("retry-after") or headers.get("Retry-After")) or (math.ceil(retry_after) if retry_after else None)
    for detail in error.get("details") or []:
        if not isinstance(detail, dict):
            continue
        kind = str(detail.get("@type", ""))
        if kind.endswith("QuotaFailure"):
            for violation in detail.get("violations") or []:
                if isinstance(violation, dict):
                    name = violation.get("quotaId") or violation.get("quotaMetric")
                    if name and str(name) not in ids:
                        ids.append(str(name))
                    limit = limit or (str(violation["quotaValue"]) if violation.get("quotaValue") is not None else None)
        elif kind.endswith("RetryInfo"):
            retry = retry or _seconds(detail.get("retryDelay"))
    code = error.get("code") or error.get("status")
    message = str(error.get("message") or "")[:MESSAGE_MAX]
    return Quota(kind=_kind(tuple(ids), code), retry_after=retry, ids=tuple(ids), limit=limit, message=message)


def classify(exc: BaseException) -> Quota | None:
    """The quota that ran out if `exc` (or what it was raised from) is a provider's 429, else None."""
    for found in _chain(exc):
        status, body, headers = _status_and_body(found)
        if status == 429:
            return _quota(body, headers, getattr(found, "retry_after", None))
    return None

"""Keep secrets out of logs and error messages."""
import re
from urllib.parse import unquote

from ..config import Config

config = Config()


def redact_rawg_key(text) -> str:
    """`requests` errors quote the whole URL, and RAWG takes its key as a `key=` query parameter."""
    text = str(text)
    key = config.RAWG_API_KEY
    return text.replace(key, "***") if key else text


_SENSITIVE_PARAM = re.compile(r"(?i)(?:^|[^a-z])(token|password|passwd|secret|key|authorization|code)(?:[^a-z]|$)")


def redact_query(query: str) -> str:
    """The query string of a request with the value of every sensitive-looking parameter masked, so a future
    `?token=` never reaches the log."""
    parts = []
    for part in query.split("&"):
        name, sep, _ = part.partition("=")
        parts.append(f"{name}=***" if sep and _SENSITIVE_PARAM.search(unquote(name)) else part)
    return "&".join(parts)

"""Keep secrets out of logs and error messages."""
from ..config import Config

config = Config()


def redact_rawg_key(text) -> str:
    """`requests` errors quote the whole URL, and RAWG takes its key as a `key=` query parameter."""
    text = str(text)
    key = config.RAWG_API_KEY
    return text.replace(key, "***") if key else text

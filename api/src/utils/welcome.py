"""The AI's welcome for somebody who joins the group (the bot sends it; this only writes it).

Whoever joins picks their own name, and the text goes to the whole group: the AI's answer is only used if it is a
short plain text that still tells them to use /activate. Anything else is None and the bot sends its fixed welcome.
"""
import re

from . import ai
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

MAX_LENGTH = 600  # the prompt asks for about 250 characters: much more means it did not follow it
ACTIVATE = re.compile(r"/activate\b")
FORMATTING = re.compile(r"[`*]")  # the bot sends it as plain text: the AI sometimes decorates the command anyway


def request_for(name: str, username: str | None) -> str:
    """What the AI is told about who joined (a name is one line: it cannot add instructions of its own)."""
    name = " ".join(name.split())
    return f"Persona que se ha unido al grupo: {name}\nUsuario de Telegram: {'@' + username if username else 'no tiene'}"


def clean(text: str) -> str | None:
    """The AI's text ready to send, or None if it cannot be sent (too long, or it forgot /activate)."""
    text = FORMATTING.sub("", text).strip()
    if not text or len(text) > MAX_LENGTH or not ACTIVATE.search(text):
        return None
    return text


def write(name: str, username: str | None) -> str | None:
    """The welcome the AI wrote, or None when it is off, fails or does not tell them to use /activate.
    It blocks on the network: call it from a worker thread."""
    if not ai.is_ready("welcome"):
        return None
    try:
        text = ai.complete(ai.prompt_for("welcome"), request_for(name, username))
    except ai.AIError as e:
        logger.error(f"AI welcome failed: {e}")
        return None
    cleaned = clean(text) if text else None
    if text and cleaned is None:
        logger.warning("The AI's welcome was discarded: too long or without /activate")
    return cleaned

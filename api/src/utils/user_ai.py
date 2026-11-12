"""A player's own AI key, for the chat and the game guide (columns `ai_api_key`, `ai_key_hint` and `ai_model` of `user_settings`).

It is the one place where the project keeps an outside service's key in the database (AGENTS.md rule 7 names the exception),
and it is kept so that nobody can read it from the app:

- It is **encrypted** (Fernet, with a key derived from the `SECRET_KEY` of the .env, apart from the one the settings use) and
  **bound to the player's id**: what is encrypted is `<id>:<key>`, so a value copied into another player's row does not open.
  A copy of the database is useless without the `SECRET_KEY`; if that changes, every key becomes unreadable and is treated as
  not set (the player is asked to enter it again).
- **No API returns it.** The player sees only whether they have one and its last four characters; nobody else, an admin
  included, sees even that. It is not loaded with the row (`deferred`), it never goes in a log or an error message, and the
  field of the request that carries it is called `api_key`, which the error reports mask.
- It is **only OpenAI's** for now (`PROVIDER`), and only the player can put it, change it or take it away.

Whether a question is paid with it or with the group's key is decided by `ai_source.resolve`."""
import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import Config
from ..database import models
from .logger import LogManager

config = Config()
logger = LogManager().get_logger()

PROVIDER = "openai"
KEY_PATTERN = re.compile(r"^sk-[A-Za-z0-9_\-]{16,300}$")  # OpenAI's: sk-..., sk-proj-...
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")
HINT_LENGTH = 4


def _fernet() -> Fernet:
    digest = hashlib.sha256(("lv-user-ai|" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(user_id: int, key: str) -> str:
    return _fernet().encrypt(f"{user_id}:{key}".encode()).decode()


def unseal(user_id: int, token: str | None) -> str | None:
    """The key a value holds, or None if it is empty, was not encrypted with this SECRET_KEY or belongs to another player."""
    if not token:
        return None
    try:
        prefix, _, key = _fernet().decrypt(token.encode()).decode().partition(":")
    except (InvalidToken, ValueError):
        return None
    return key if prefix == str(user_id) and key else None


def clean_key(value) -> str | None:
    """The key trimmed if it looks like one of OpenAI's, else None."""
    key = str(value or "").strip()
    return key if KEY_PATTERN.fullmatch(key) else None


def clean_model(value) -> str | None:
    model = str(value or "").strip()
    return model if MODEL_PATTERN.fullmatch(model) else None


def hint_of(key: str) -> str:
    return key[-HINT_LENGTH:]


def _row(db: Session, user_id: int, create: bool = False) -> models.UserSettings | None:
    row = db.get(models.UserSettings, user_id)
    if row is None and create:
        row = models.UserSettings(user_id=user_id)
        db.add(row)
    return row


def status(db: Session, user_id: int) -> dict:
    """What the player may see of their own key: whether there is one, its last characters and the model. `unreadable` is
    a key that is stored but cannot be opened (the SECRET_KEY changed): the player has to enter it again."""
    row = _row(db, user_id)
    token = row.ai_api_key if row else None
    readable = unseal(user_id, token) is not None
    return {
        "has_key": readable,
        "unreadable": bool(token) and not readable,
        "hint": row.ai_key_hint if readable else None,
        "model": row.ai_model if readable else None,
        "provider": PROVIDER,
    }


def model_of(db: Session, user_id: int) -> str | None:
    """The model the player chose, even if the key it was chosen for cannot be opened any more: replacing the key keeps it."""
    row = _row(db, user_id)
    return row.ai_model if row else None


def credentials(db: Session, user_id: int) -> tuple[str, str] | None:
    """(key, model) of the player's own, or None if they have none (or it cannot be opened)."""
    row = _row(db, user_id)
    key = unseal(user_id, row.ai_api_key) if row else None
    if key is None or not row.ai_model:
        return None
    return key, row.ai_model


def save(db: Session, user_id: int, key: str, model: str) -> None:
    row = _row(db, user_id, create=True)
    row.ai_api_key = seal(user_id, key)
    row.ai_key_hint = hint_of(key)
    row.ai_model = model
    db.commit()


def set_model(db: Session, user_id: int, model: str) -> bool:
    """Changes the model of a key already saved; False if there is none to change."""
    row = _row(db, user_id)
    if row is None or unseal(user_id, row.ai_api_key) is None:
        return False
    row.ai_model = model
    db.commit()
    return True


def clear(db: Session, user_id: int) -> None:
    row = _row(db, user_id)
    if row is not None:
        row.ai_api_key = None
        row.ai_key_hint = None
        row.ai_model = None
        db.commit()

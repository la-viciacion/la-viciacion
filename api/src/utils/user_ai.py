"""A player's own AI keys, one for each provider, for the chat and the game guide (tables `user_ai_vault` and `user_ai_keys`, and the
column `ai_provider` of `user_settings`).

It is one of the places where the project keeps an outside service's key in the database (AGENTS.md rule 7 names the exception), and
it is kept so that no copy of the server can read it:

- It is **sealed with a data key that only the player's password opens** (utils/ai_vault.py): a copy of the database, and even of the
  database with the `.env`, holds nothing a key can be read from. The session of a logged-in player carries the data key in its token
  (`auth.get_unlock`), so the keys can be used while the session lasts, and a session that does not carry it (an old one, one made after
  the vault was lost) is **locked** until the player types their password again.
- **No API returns it.** The player sees whether they have one, its last four characters (only while unlocked: the hint is inside the
  sealed value, not in a column) and the model; nobody else, an admin included, sees even that. It never goes in a log or an error
  message, and the field of the request that carries it is called `api_key`, which the error reports mask.
- Only the player can put it, change it or take it away. A password that is **reset** (a recovery link, an admin) cannot open the vault:
  its keys are deleted (`wipe`), and the player pastes them again. Changing one's own password wraps the same data key again (`rewrap`).

Whether a question is paid with one of them or with the group's key is decided by `ai_source.decide`."""
import json
import re

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import Config
from ..database import models
from . import ai_vault, settings
from .logger import LogManager

config = Config()
logger = LogManager().get_logger()

PROVIDERS = settings.AI_PROVIDERS
# What a key of each provider looks like. OpenAI's `sk-...` also matches the start of the other two (`sk-ant-`, `sk-or-`): they are excluded
KEY_PATTERNS = {
    "openai": re.compile(r"^sk-(?!ant-|or-)[A-Za-z0-9_\-]{16,300}$"),
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_\-]{16,300}$"),
    "openrouter": re.compile(r"^sk-or-[A-Za-z0-9_\-]{16,300}$"),
    "google": re.compile(r"^AIza[A-Za-z0-9_\-]{20,60}$"),
}
# The model a key starts with when the player does not choose one: any of them can be changed from the list of the key's own provider
DEFAULT_MODELS = {"openai": "gpt-4.1-mini", "google": "gemini-3.5-flash-lite", "anthropic": "claude-haiku-5-5", "openrouter": "openai/gpt-4.1-mini"}
# Which provider's key comes first when nothing says (the player's preference, the group's own provider)
ORDER = ("openai", "anthropic", "google", "openrouter")
HINT_LENGTH = 4


def clean_key(provider: str, value) -> str | None:
    """The key trimmed if it looks like one of `provider`'s, else None."""
    key = str(value or "").strip()
    pattern = KEY_PATTERNS.get(provider)
    return key if pattern and pattern.fullmatch(key) else None


def clean_model(value) -> str | None:
    model = str(value or "").strip()
    return model if settings.MODEL_NAME.fullmatch(model) else None


def hint_of(key: str) -> str:
    return key[-HINT_LENGTH:]


# ── the vault ────────────────────────────────────────────────────────────────
def _vault_row(db: Session, user_id: int) -> models.UserAiVault | None:
    return db.get(models.UserAiVault, user_id)


def _store_vault(db: Session, user_id: int, record: dict) -> None:
    row = _vault_row(db, user_id)
    if row is None:
        db.add(models.UserAiVault(user_id=user_id, record=json.dumps(record)))
    else:
        row.record = json.dumps(record)


def _open(db: Session, user_id: int, password: str) -> bytes | None:
    row = _vault_row(db, user_id)
    if row is None:
        return None
    try:
        return ai_vault.open_vault(user_id, json.loads(row.record), password)
    except ValueError:
        return None


def unlock(db: Session, user_id: int, password: str, create: bool = True) -> bytes | None:
    """The data key for a player who has just proved their password: opened from their vault or, if they have none and `create`, a
    new vault. None if there is nothing to open (no vault, and `create` is off) or the vault does not open (it was made for another
    password: it cannot happen unless something wrote it badly). The legacy key, if there is one, is adopted into it."""
    dek = _open(db, user_id, password)
    if dek is None and _vault_row(db, user_id) is None and (create or has_legacy(db, user_id)):
        record, dek = ai_vault.create(user_id, password)
        _store_vault(db, user_id, record)
    if dek is not None:
        adopt_legacy(db, user_id, dek)
    db.commit()
    return dek


def rewrap(db: Session, user_id: int, old_password: str, new_password: str) -> None:
    """Their own password changed: the same data key, wrapped with the new one. A vault that the old password does not open cannot be
    kept (nobody can read it any more): it is deleted with its keys."""
    if _vault_row(db, user_id) is None:
        return
    dek = _open(db, user_id, old_password)
    if dek is None:
        wipe(db, user_id)
        return
    _store_vault(db, user_id, ai_vault.wrap(user_id, dek, new_password))
    db.commit()


def wipe(db: Session, user_id: int) -> bool:
    """Deletes the vault and every key of a player whose password was reset: nothing can open them. True if there was something."""
    keys = db.query(models.UserAiKey).filter(models.UserAiKey.user_id == user_id).delete(synchronize_session=False)
    vault = db.query(models.UserAiVault).filter(models.UserAiVault.user_id == user_id).delete(synchronize_session=False)
    row = db.get(models.UserSettings, user_id)
    if row is not None:
        row.ai_provider = None
    db.commit()
    return bool(keys or vault)


# ── the legacy key: one OpenAI key, kept before the vault with a key of the server ─────────────
def _legacy_fernet() -> Fernet:
    import base64
    import hashlib

    digest = hashlib.sha256(("lv-user-ai|" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def legacy_unseal(user_id: int, token: str | None) -> str | None:
    """The key a legacy value holds, or None if it is empty, was not encrypted with this SECRET_KEY or belongs to another player."""
    if not token:
        return None
    try:
        prefix, _, key = _legacy_fernet().decrypt(token.encode()).decode().partition(":")
    except (InvalidToken, ValueError):
        return None
    return key if prefix == str(user_id) and key else None


def has_legacy(db: Session, user_id: int) -> bool:
    row = db.get(models.UserSettings, user_id)
    return bool(row is not None and row.ai_api_key)


def adopt_legacy(db: Session, user_id: int, dek: bytes) -> bool:
    """Moves the old OpenAI key of a player into their vault (sealed with `dek`) and empties the old columns. A key that cannot be
    opened (the SECRET_KEY changed) is dropped, as it was shown to the player as unreadable. Does not commit."""
    row = db.get(models.UserSettings, user_id)
    if row is None or not row.ai_api_key:
        return False
    key = legacy_unseal(user_id, row.ai_api_key)
    if key is not None and db.get(models.UserAiKey, (user_id, "openai")) is None:
        db.add(models.UserAiKey(user_id=user_id, provider="openai", secret=ai_vault.seal_key(dek, user_id, "openai", key), model=row.ai_model or DEFAULT_MODELS["openai"]))
    row.ai_api_key = None
    row.ai_key_hint = None
    row.ai_model = None
    return key is not None


# ── the keys ─────────────────────────────────────────────────────────────────
def _row(db: Session, user_id: int, provider: str) -> models.UserAiKey | None:
    return db.get(models.UserAiKey, (user_id, provider))


def providers_with_key(db: Session, user_id: int) -> list[str]:
    """The providers the player has a key for (even while locked), in `ORDER`; the legacy OpenAI one counts."""
    found = {r.provider for r in db.query(models.UserAiKey.provider).filter(models.UserAiKey.user_id == user_id).all()}
    if has_legacy(db, user_id):
        found.add("openai")
    return [p for p in ORDER if p in found]


def preferred(db: Session, user_id: int) -> str | None:
    row = db.get(models.UserSettings, user_id)
    return row.ai_provider if row is not None and row.ai_provider in PROVIDERS else None


def set_preferred(db: Session, user_id: int, provider: str | None) -> None:
    row = db.get(models.UserSettings, user_id)
    if row is None:
        row = models.UserSettings(user_id=user_id)
        db.add(row)
    row.ai_provider = provider
    db.commit()


def status(db: Session, user_id: int, dek: bytes | None) -> dict:
    """What the player may see of their own keys. `unlocked`: this session carries the data key (without it nothing can be saved or used:
    the player types their password). `locked`: they have keys that it cannot open. Per provider: whether there is a key, its last characters (only while unlocked), the model, and `unreadable` for a
    key that is stored but does not open with the data key of the session."""
    held = providers_with_key(db, user_id)
    keys = {}
    for provider in PROVIDERS:
        row = _row(db, user_id, provider)
        if provider not in held:
            keys[provider] = {"has_key": False, "hint": None, "model": None, "unreadable": False}
            continue
        key = ai_vault.unseal_key(dek, user_id, provider, row.secret) if dek is not None and row is not None else None
        keys[provider] = {
            "has_key": True,
            "hint": hint_of(key) if key else None,
            "model": row.model if row is not None else None,
            "unreadable": bool(dek is not None and row is not None and key is None),
        }
    return {
        "unlocked": dek is not None,  # this session carries the data key: keys can be saved and used (a player with none yet is not unlocked either)
        "locked": bool(held) and dek is None,
        "preferred": preferred(db, user_id),
        "keys": keys,
        "default_models": DEFAULT_MODELS,
    }


def credentials(db: Session, user_id: int, dek: bytes | None, provider: str) -> tuple[str, str] | None:
    """(key, model) of the player's own for `provider`, or None if they have none or this session cannot open it."""
    row = _row(db, user_id, provider)
    if row is None or dek is None:
        return None
    key = ai_vault.unseal_key(dek, user_id, provider, row.secret)
    return (key, row.model or DEFAULT_MODELS[provider]) if key else None


def save(db: Session, user_id: int, dek: bytes, provider: str, key: str, model: str | None = None) -> None:
    """Saves (or replaces) the key of `provider`. Replacing keeps the model unless one is given."""
    row = _row(db, user_id, provider)
    sealed = ai_vault.seal_key(dek, user_id, provider, key)
    if row is None:
        db.add(models.UserAiKey(user_id=user_id, provider=provider, secret=sealed, model=model or DEFAULT_MODELS[provider]))
    else:
        row.secret = sealed
        row.model = model or row.model or DEFAULT_MODELS[provider]
    db.commit()


def set_model(db: Session, user_id: int, provider: str, model: str) -> bool:
    """Changes the model of a key already saved; False if there is none to change."""
    row = _row(db, user_id, provider)
    if row is None:
        return False
    row.model = model
    db.commit()
    return True


def clear(db: Session, user_id: int, provider: str) -> None:
    """Takes the key of `provider` away (and the preference for it, if it was the preferred)."""
    db.query(models.UserAiKey).filter(models.UserAiKey.user_id == user_id, models.UserAiKey.provider == provider).delete(synchronize_session=False)
    row = db.get(models.UserSettings, user_id)
    if row is not None and row.ai_provider == provider:
        row.ai_provider = None
    if row is not None and provider == "openai":  # one that was not adopted yet is the same key
        row.ai_api_key = row.ai_key_hint = row.ai_model = None
    db.commit()

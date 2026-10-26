"""Runtime settings edited from the admin panel (table `app_settings`).

Every setting is declared once in REGISTRY (type, default, validation, whether
it is a secret). The table stores values as text; secrets (the push private key)
are encrypted with a key derived from SECRET_KEY and are never returned by the
API, only a hint of their last characters.

A setting with `env_only` is not in the table: the keys of outside services (the Telegram token and chats, the AI key)
and the AI provider and model (and the chat's model, which falls back to the AI's). They are read from the environment every time and never stored, so a copy of the
database (a backup, a dump loaded on a laptop) cannot use them, which only whoever holds the .env should be able to do,
and the panel cannot change them.
"""
import base64
import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import Config
from ..database import models
from ..database.database import SessionLocal
from ..chat.prompt import CHAT_PROMPT
from .ai_prompts import USES as AI_USES
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

CACHE_SECONDS = 10


@dataclass(frozen=True)
class Spec:
    type: str  # "bool" | "int" | "str"
    default: Any = None
    secret: bool = False
    hint: bool = True  # a secret shows its last characters in the panel unless this is False
    env: str | None = None  # variable that seeds the value the first time (the one it is read from, if env_only)
    check: Callable[[Any], str | None] | None = None  # error message or None
    blank_ok: bool = False  # an empty text is a valid value (it means "the default")
    resettable: bool = False  # `None` deletes the stored value, so the default applies again
    env_only: bool = False  # read from the environment (`env`) every time, never stored: the panel shows whether it is set and cannot change it


def _chat_id(value: str) -> str | None:
    return None if re.fullmatch(r"-?\d{1,20}", value) else "Debe ser un número (los grupos empiezan por -)"


def _token(value: str) -> str | None:
    return None if re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", value) else "No parece un token de bot de Telegram"


def _time(value: str) -> str | None:
    return None if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value) else "La hora debe tener formato HH:MM"


def _weekday(value: int) -> str | None:
    return None if 0 <= value <= 6 else "El día debe estar entre 0 (lunes) y 6 (domingo)"


# How the group hears about the wished games that come out: the day before, once a week, or not at all
WISHLIST_GROUP_NOTICES = ("eve", "weekly", "off")


def _wishlist_group_notice(value: str) -> str | None:
    return None if value in WISHLIST_GROUP_NOTICES else "Debe ser eve (la víspera), weekly (semanal) u off (ninguno)"


def _monthly_day(value: int) -> str | None:
    return None if 1 <= value <= 5 else "El día debe estar entre 1 y 5"


# The season's recap goes out when the year is about to end or has just ended: the days each month allows
ANNUAL_DAYS = {12: range(20, 29), 1: range(1, 6)}


def _annual_month(value: int) -> str | None:
    return None if value in ANNUAL_DAYS else "El resumen anual se envía en diciembre (12) o en enero (1)"


def _annual_day(value: int) -> str | None:
    return None if 1 <= value <= 28 else "El día debe estar entre 1 y 28"


def check_annual(month: int, day: int) -> str | None:
    """The month and the day of the annual recap together: December 20-28 or January 1-5."""
    days = ANNUAL_DAYS[month]
    return None if day in days else f"En {'diciembre' if month == 12 else 'enero'} el resumen anual se envía entre el {days[0]} y el {days[-1]}"


def _contact(value: str) -> str | None:
    return None if re.fullmatch(r"(mailto:[^@\s]+@[^@\s]+|https://\S+)", value) else "Debe ser mailto:correo@dominio o una URL https"


def _vapid_public(value: str) -> str | None:
    return None if re.fullmatch(r"[A-Za-z0-9_-]{80,100}", value) else "Clave pública VAPID no válida"


INBOX_RETENTION_MAX = 365


def _retention(value: int) -> str | None:
    return None if 1 <= value <= INBOX_RETENTION_MAX else f"Los días deben estar entre 1 y {INBOX_RETENTION_MAX}"


PROMPT_MAX = 4000

LIMIT_MAX = 100000


def _limit(value: int) -> str | None:
    return None if 0 <= value <= LIMIT_MAX else f"Debe estar entre 0 (sin límite) y {LIMIT_MAX}"


def _prompt(value: str) -> str | None:
    return None if len(value) <= PROMPT_MAX else f"Como máximo {PROMPT_MAX} caracteres"


REGISTRY: dict[str, Spec] = {
    "notifications.enabled": Spec("bool", True),
    "notifications.admin_alerts": Spec("bool", True),
    # Suggest another game at the end of the completion notice (by the AI or as a fixed line when it does not write it)
    "completed_game.recommend": Spec("bool", True),
    "weekly.enabled": Spec("bool", True),
    "weekly.weekday": Spec("int", 0, check=_weekday),  # 0 = Monday
    "weekly.time": Spec("str", "09:00", check=_time),
    # The group's notice of the wished games that come out: one mode at a time, so the two never both go out
    "wishlist.group_notice": Spec("str", "eve", check=_wishlist_group_notice),
    # The time of either one: every day for "eve", on Sundays (scheduler.WISHLIST_WEEKLY_WEEKDAY) for "weekly".
    # After the 09:00 release-date refresh, so a date that slipped is already corrected when the group is told
    "wishlist.time": Spec("str", "12:30", check=_time),
    # Off until an admin has seen it in the panel (Notificaciones → Probar resumen)
    "monthly.enabled": Spec("bool", False),
    "monthly.day": Spec("int", 1, check=_monthly_day),  # day of the month, in the first days: the app offers it from the 1st to the 5th
    "monthly.time": Spec("str", "10:00", check=_time),
    # The season's recap, apart from the monthly one: December 20-28 or January 1-5 (checked together in set_values)
    "annual.enabled": Spec("bool", False),
    "annual.month": Spec("int", 1, check=_annual_month),
    "annual.day": Spec("int", 1, check=_annual_day),
    "annual.time": Spec("str", "10:00", check=_time),
    # 0 = the running season's recap is locked (crud.recap.season_locked); any other value is the year it was
    # unlocked for, so it locks itself again once that year is no longer the running one. Set by hand from the
    # panel, or automatically the moment its notice reaches the group (utils/recap_notices.announce_recap).
    "annual.unlocked_year": Spec("int", 0),
    # Off: a player opens a recap only in the first days after it (crud.recap.recap_closed); on: any finished one, always
    "recap.always_available": Spec("bool", False),
    # Web Push (utils/push.py). The keys are generated from the panel, never typed.
    "push.enabled": Spec("bool", True),
    "push.contact": Spec("str", None, check=_contact),
    "push.vapid_public": Spec("str", None, check=_vapid_public),
    "push.vapid_private": Spec("str", None, secret=True, hint=False),
    # The deployment the keys were made for (utils/push.current_origin): a database copied to another one keeps keys that
    # still reach the devices of the first, so push stays off until the keys are made again there.
    "push.vapid_origin": Spec("str", None),
    # Days the app's notification inbox keeps a notice before the scheduler purges it (utils/inbox.py)
    "inbox.retention_days": Spec("int", 14, check=_retention),
    # AI text for the notices (utils/ai.py). The key is AI_API_KEY and is never stored;
    # the provider and the model are read from AI_PROVIDER and AI_MODEL every time; there is no default for either.
    "ai.enabled": Spec("bool", True),
    "ai.provider": Spec("str", None, env="AI_PROVIDER", env_only=True),  # "google" or "openai" (utils/ai.py PROVIDERS)
    "ai.api_key": Spec("str", None, secret=True, env_only=True, env="AI_API_KEY"),
    "ai.model": Spec("str", None, env="AI_MODEL", env_only=True),  # no default in the code: without it the AI does not write
    # The chat assistant (chat/): its own switch and instructions. It talks to the same provider with the same key as the
    # notices (ai.provider, ai.api_key); only the model may be its own (CHAT_AI_MODEL, optional: without it, ai.model).
    "chat.enabled": Spec("bool", True),
    "chat.model": Spec("str", None, env="CHAT_AI_MODEL", env_only=True),
    # Questions the chat answers (routers/chat.py), 0 = no limit: per player in the last minute, hour and 24 hours, and
    # in all for the group (the provider's quota is the project's, not each player's)
    "chat.limit_user_minute": Spec("int", 5, check=_limit),
    "chat.limit_user_hour": Spec("int", 30, check=_limit),
    "chat.limit_user_day": Spec("int", 100, check=_limit),
    "chat.limit_group_minute": Spec("int", 10, check=_limit),
    "chat.limit_group_day": Spec("int", 300, check=_limit),
    "chat.prompt": Spec("str", CHAT_PROMPT.strip(), check=_prompt, resettable=True),
    "telegram.token": Spec("str", None, secret=True, env_only=True, env="TELEGRAM_TOKEN", check=_token),
    "telegram.group_id": Spec("str", None, env_only=True, env="TELEGRAM_GROUP_ID", check=_chat_id),
    "telegram.admin_chat_id": Spec("str", None, env_only=True, env="TELEGRAM_ADMIN_CHAT_ID", check=_chat_id),
}

# One prompt (default: the one in the code) and one switch per place the AI writes (utils/ai_prompts.py).
for _id, _use in AI_USES.items():
    REGISTRY[f"ai.prompt.{_id}"] = Spec("str", _use.default.strip(), check=_prompt, resettable=True)
    if _use.switchable:
        REGISTRY[f"ai.use.{_id}"] = Spec("bool", True)


# ── encoding ────────────────────────────────────────────────
def _fernet() -> Fernet:
    digest = hashlib.sha256(("lv-settings|" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def coerce(key: str, value: Any) -> Any:
    """Validate `value` for `key` and return it with its proper type (ValueError otherwise)."""
    spec = REGISTRY[key]
    if spec.type == "bool":
        if isinstance(value, bool):
            result = value
        elif str(value).lower() in ("1", "true", "yes", "on"):
            result = True
        elif str(value).lower() in ("0", "false", "no", "off"):
            result = False
        else:
            raise ValueError(f"{key}: debe ser verdadero o falso")
    elif spec.type == "int":
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: debe ser un número entero") from None
    else:
        result = str(value).strip()
        if not result and not spec.blank_ok:
            raise ValueError(f"{key}: no puede estar vacío")
    if spec.check and not (spec.blank_ok and result == ""):
        error = spec.check(result)
        if error:
            raise ValueError(f"{key}: {error}")
    return result


def _encode(key: str, value: Any) -> str:
    spec = REGISTRY[key]
    text = ("1" if value else "0") if spec.type == "bool" else str(value)
    return _fernet().encrypt(text.encode()).decode() if spec.secret else text


def _decode(key: str, raw: str | None) -> Any:
    spec = REGISTRY[key]
    if raw is None:
        return spec.default
    if spec.secret:
        try:
            raw = _fernet().decrypt(raw.encode()).decode()
        except InvalidToken:
            logger.error(f"Cannot decrypt {key}: SECRET_KEY changed? Set it again from the admin panel.")
            return None
    if spec.type == "bool":
        return raw == "1"
    if spec.type == "int":
        return int(raw)
    return raw


# ── reads (cached: every notification asks for them) ────────
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _from_env(spec: Spec) -> str | None:
    return (os.getenv(spec.env) or "").strip() or None


def get(key: str) -> Any:
    spec = REGISTRY[key]
    if spec.env_only:
        return _from_env(spec)  # the environment is not worth caching, and a test or an operator may change it
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    with SessionLocal() as db:
        row = db.get(models.AppSetting, key)
        value = _decode(key, row.value if row else None)
    with _lock:
        _cache[key] = (now, value)
    return value


def get_all(db: Session) -> dict[str, Any]:
    rows = {r.key: r.value for r in db.query(models.AppSetting).all()}
    return {key: _from_env(spec) if spec.env_only else _decode(key, rows.get(key)) for key, spec in REGISTRY.items()}


def customized(db: Session) -> set[str]:
    """Resettable settings the admin has changed (the rest follow the defaults in the code)."""
    stored = {r.key for r in db.query(models.AppSetting).all()}
    return {key for key, spec in REGISTRY.items() if spec.resettable and key in stored}


def ai_uses(db: Session) -> list[dict]:
    """Where the AI writes, for the panel: each with the prompt the code brings and whether the admin changed it."""
    changed = customized(db)
    return [
        {
            "id": use_id,
            "label": use.label,
            "help": use.help,
            "switchable": use.switchable,
            "parent": use.parent,
            "switch": f"ai.use.{use_id}" if use.switchable else use.switch,
            "default_prompt": REGISTRY[f"ai.prompt.{use_id}"].default,
            "customized": f"ai.prompt.{use_id}" in changed,
        }
        for use_id, use in AI_USES.items()
    ]


def chat_prompt(db: Session) -> dict:
    """The chat's instructions, for the panel: the prompt the code brings and whether the admin changed it."""
    return {"default_prompt": REGISTRY["chat.prompt"].default, "customized": "chat.prompt" in customized(db)}


def public_view(db: Session) -> dict[str, Any]:
    """Values for the admin panel; a secret is reduced to whether it is set and its last characters, a locked
    setting to whether it is set."""
    values = get_all(db)
    out = {}
    for key, spec in REGISTRY.items():
        if spec.secret or spec.env_only:
            secret = values[key]
            show_hint = spec.secret and spec.hint and not spec.env_only
            out[key] = {"is_set": bool(secret), "hint": ("…" + secret[-4:]) if secret and show_hint else None}
        else:
            out[key] = values[key]
    return out


# ── writes ──────────────────────────────────────────────────
def set_values(db: Session, values: dict[str, Any], user_id: int | None = None) -> list[str]:
    """Validate and store several settings at once (all or none). Returns the keys that changed."""
    clean = {}
    for key, value in values.items():
        if key not in REGISTRY:
            raise ValueError(f"Ajuste desconocido: {key}")
        if REGISTRY[key].env_only:
            raise ValueError(f"{key}: se configura en el .env del servidor, no se guarda en la base de datos")
        if value is None and REGISTRY[key].resettable:
            clean[key] = None
            continue
        if value is None:
            raise ValueError(f"{key}: no puede estar vacío")
        clean[key] = coerce(key, value)
    current = get_all(db)
    if any(key.startswith("annual.") for key in clean):
        effective = {**current, **{key: value for key, value in clean.items() if value is not None}}
        problem = check_annual(effective["annual.month"], effective["annual.day"])
        if problem:
            raise ValueError(problem)
    changed = []
    for key, value in clean.items():
        if value is None:  # back to the default
            row = db.get(models.AppSetting, key)
            if row is not None:
                db.delete(row)
                changed.append(key)
            continue
        if current.get(key) == value:
            continue
        row = db.get(models.AppSetting, key)
        if row is None:
            db.add(models.AppSetting(key=key, value=_encode(key, value), updated_by=user_id))
        else:
            row.value = _encode(key, value)
            row.updated_by = user_id
        changed.append(key)
    db.commit()
    with _lock:
        for key in changed:
            _cache.pop(key, None)
    return changed

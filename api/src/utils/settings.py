"""Runtime settings edited from the admin panel (table `app_settings`).

Every setting is declared once in REGISTRY (type, default, validation, whether
it is a secret). The table stores values as text; secrets (the Telegram token, the AI key)
are encrypted with a key derived from SECRET_KEY and are never returned by the
API, only a hint of their last characters.

The .env values named in `env` only seed the table the first time (see
seed_from_env): from then on the database is the source of truth.
"""
import base64
import hashlib
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
    env: str | None = None  # variable that seeds the value the first time
    check: Callable[[Any], str | None] | None = None  # error message or None
    blank_ok: bool = False  # an empty text is a valid value (it means "the default")
    resettable: bool = False  # `None` deletes the stored value, so the default applies again


def _chat_id(value: str) -> str | None:
    return None if re.fullmatch(r"-?\d{1,20}", value) else "Debe ser un número (los grupos empiezan por -)"


def _token(value: str) -> str | None:
    return None if re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", value) else "No parece un token de bot de Telegram"


def _time(value: str) -> str | None:
    return None if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value) else "La hora debe tener formato HH:MM"


def _weekday(value: int) -> str | None:
    return None if 0 <= value <= 6 else "El día debe estar entre 0 (lunes) y 6 (domingo)"


def _contact(value: str) -> str | None:
    return None if re.fullmatch(r"(mailto:[^@\s]+@[^@\s]+|https://\S+)", value) else "Debe ser mailto:correo@dominio o una URL https"


def _vapid_public(value: str) -> str | None:
    return None if re.fullmatch(r"[A-Za-z0-9_-]{80,100}", value) else "Clave pública VAPID no válida"


AI_PROVIDERS = ("google", "openai")


def _ai_provider(value: str) -> str | None:
    return None if value in AI_PROVIDERS else "El proveedor debe ser " + " u ".join(AI_PROVIDERS)


def _ai_model(value: str) -> str | None:
    # it goes into the URL of the request, so only what model names are made of
    return None if not value or re.fullmatch(r"[A-Za-z0-9._-]{1,100}", value) else "Nombre de modelo no válido"


PROMPT_MAX = 4000


def _prompt(value: str) -> str | None:
    return None if len(value) <= PROMPT_MAX else f"Como máximo {PROMPT_MAX} caracteres"


REGISTRY: dict[str, Spec] = {
    "notifications.enabled": Spec("bool", True),
    "notifications.admin_alerts": Spec("bool", True),
    "weekly.enabled": Spec("bool", True),
    "weekly.weekday": Spec("int", 0, check=_weekday),  # 0 = Monday
    "weekly.time": Spec("str", "09:00", check=_time),
    # Web Push (utils/push.py). The keys are generated from the panel, never typed.
    "push.enabled": Spec("bool", True),
    "push.contact": Spec("str", None, check=_contact),
    "push.vapid_public": Spec("str", None, check=_vapid_public),
    "push.vapid_private": Spec("str", None, secret=True, hint=False),
    # AI text for the notices (utils/ai.py). The key is typed in the panel; AI_* (or the old OPENAI_*) only seed it.
    "ai.enabled": Spec("bool", True),
    "ai.provider": Spec("str", "google", env="AI_PROVIDER", check=_ai_provider),
    "ai.api_key": Spec("str", None, secret=True, env="AI_API_KEY"),
    "ai.model": Spec("str", None, env="AI_MODEL", check=_ai_model, blank_ok=True),  # empty: the provider's default
    "telegram.token": Spec("str", None, secret=True, env="TELEGRAM_TOKEN", check=_token),
    "telegram.group_id": Spec("str", None, env="TELEGRAM_GROUP_ID", check=_chat_id),
    "telegram.admin_chat_id": Spec("str", None, env="TELEGRAM_ADMIN_CHAT_ID", check=_chat_id),
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


def get(key: str) -> Any:
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
    return {key: _decode(key, rows.get(key)) for key in REGISTRY}


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
            "default_prompt": REGISTRY[f"ai.prompt.{use_id}"].default,
            "customized": f"ai.prompt.{use_id}" in changed,
        }
        for use_id, use in AI_USES.items()
    ]


def public_view(db: Session) -> dict[str, Any]:
    """Values for the admin panel; a secret is reduced to whether it is set and its last characters."""
    values = get_all(db)
    out = {}
    for key, spec in REGISTRY.items():
        if spec.secret:
            secret = values[key]
            out[key] = {"is_set": bool(secret), "hint": ("…" + secret[-4:]) if secret and spec.hint else None}
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
        if value is None and REGISTRY[key].resettable:
            clean[key] = None
            continue
        if value is None:
            raise ValueError(f"{key}: no puede estar vacío")
        clean[key] = coerce(key, value)
    current = get_all(db)
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


def seed_from_env(db: Session) -> list[str]:
    """Copy the .env values into settings that do not exist yet (first start only)."""
    import os

    seeded: list[str] = []
    for key, spec in REGISTRY.items():
        if not spec.env or db.get(models.AppSetting, key) is not None:
            continue
        raw = os.getenv(spec.env)
        if not raw:
            continue
        try:
            value = coerce(key, raw)
        except ValueError as e:
            logger.warning(f"Not seeding {key} from {spec.env}: {e}")
            continue
        db.add(models.AppSetting(key=key, value=_encode(key, value)))
        seeded.append(key)
    seeded += _seed_legacy_openai(db, seeded)
    db.commit()
    if seeded:
        logger.info("Settings seeded from environment: " + ", ".join(seeded))
    return seeded


def _seed_legacy_openai(db: Session, seeded: list[str]) -> list[str]:
    """Installations from before the AI settings have OPENAI_API_KEY (and OPENAI_MODEL): they keep
    working as the "openai" provider unless AI_* says otherwise."""
    import os

    legacy = {
        "ai.api_key": os.getenv("OPENAI_API_KEY"),
        "ai.provider": "openai",
        "ai.model": os.getenv("OPENAI_MODEL"),
    }
    if not legacy["ai.api_key"] or "ai.api_key" in seeded or db.get(models.AppSetting, "ai.api_key") is not None:
        return []
    added = []
    for key, raw in legacy.items():
        if not raw or key in seeded or db.get(models.AppSetting, key) is not None:
            continue
        try:
            db.add(models.AppSetting(key=key, value=_encode(key, coerce(key, raw))))
        except ValueError as e:
            logger.warning(f"Not seeding {key} from the OPENAI_* variables: {e}")
            continue
        added.append(key)
    return added


def telegram_version(db: Session) -> str:
    """Changes whenever the token or a chat id changes (the bot restarts on it)."""
    values = get_all(db)
    raw = "|".join(str(values[k]) for k in ("telegram.token", "telegram.group_id", "telegram.admin_chat_id"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

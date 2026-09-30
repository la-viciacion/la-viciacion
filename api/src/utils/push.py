"""Web Push: notifications for the installed PWA (the second channel next to Telegram).

Everything is off until an admin generates the VAPID keys and enables `push.enabled`
in the panel. Nothing here may break the Telegram path: every public function
swallows its errors and only logs them.

- notify_group: a copy of what goes to the Telegram group, for every device that
  wants group notices.
- notify_user: a private notice for one user, on all of their devices.

Payloads are short plain text (title, body, url, tag): how long messages and images
fit into a push is still to be designed, see docs/roadmap.md.
"""
import asyncio
import base64
import json
import re

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import select

from ..config import Config
from ..database import models
from ..database.database import SessionLocal
from . import settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

APP_NAME = "La Viciación"
TITLE_MAX = 80
BODY_MAX = 200
ANNOUNCEMENT_BODY_MAX = 240
PAYLOAD_MAX_BYTES = 3500  # the Web Push limit is 4096 bytes once encrypted
TTL_SECONDS = 3600  # a notice that could not be delivered within the hour is stale
MAX_DEVICES_PER_USER = 10


# ── payload ─────────────────────────────────────────────────
def plain_text(message: str) -> str:
    """Telegram Markdown to plain text."""
    text = re.sub(r"\\(.)", r"\1", str(message))
    return re.sub(r"[*_`]", "", text)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_payload(message: str, url: str = "/", tag: str | None = None) -> dict:
    """First line becomes the title and the rest the body; a one-liner gets the app name as title."""
    lines = [line.strip() for line in plain_text(message).splitlines() if line.strip()]
    if not lines:
        title, body = APP_NAME, ""
    elif len(lines) == 1:
        title, body = APP_NAME, lines[0]
    else:
        title, body = lines[0], " · ".join(lines[1:])
    return {"title": _shorten(title, TITLE_MAX), "body": _shorten(body, BODY_MAX), "url": url, "tag": tag}


def build_announcement(title: str, body: str | None = None, url: str | None = None, image: str | None = None) -> dict:
    """A notice written by an admin. Raises ValueError with a message for the panel if it cannot be sent.

    Plain text only (no Markdown or HTML). `url` is where a tap opens the app (a path or a #/ route of
    this site), `image` an https picture shown large on Android and desktop (iOS ignores it).
    """
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("El título es obligatorio")
    if len(title) > TITLE_MAX:
        raise ValueError(f"El título admite {TITLE_MAX} caracteres como máximo")
    if len(body) > ANNOUNCEMENT_BODY_MAX:
        raise ValueError(f"El mensaje admite {ANNOUNCEMENT_BODY_MAX} caracteres como máximo")
    url = (url or "").strip() or "/"
    if not re.fullmatch(r"(/(?!/)|#/)[\w\-./?=&%#]*", url):
        raise ValueError("El enlace debe ser una ruta de la app (por ejemplo / o #/profile)")
    image = (image or "").strip() or None
    if image and not re.fullmatch(r"https://[^\s]{4,480}", image):
        raise ValueError("La imagen debe ser una URL https")
    payload = {"title": title, "body": body, "url": url, "tag": None}
    if image:
        payload["image"] = image
    if len(json.dumps(payload).encode()) > PAYLOAD_MAX_BYTES:
        raise ValueError("El aviso es demasiado grande")
    return payload


# ── keys and settings ───────────────────────────────────────
def generate_vapid_keys() -> tuple[str, str]:
    """(public key as base64url for the browser, private key as PEM)."""
    vapid = Vapid()
    vapid.generate_keys()
    public = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(public).rstrip(b"=").decode(), vapid.private_pem().decode()


def contact() -> str:
    """Contact the push services can use to reach the sender (mailto: or https: URL)."""
    return settings.get("push.contact") or f"mailto:{config.SMTP_EMAIL}"


def is_ready() -> bool:
    return bool(settings.get("push.enabled") and settings.get("push.vapid_public") and settings.get("push.vapid_private"))


def ensure_vapid_keys(db) -> bool:
    """Create the server's VAPID keys on the first start (or when the stored ones cannot be read).

    There is one pair for the whole server, never one per user. If the private key is
    missing or unreadable (SECRET_KEY changed), the old public key is useless: new keys are
    made and every device is dropped, because it subscribed to the old ones.
    Returns True if keys were created.
    """
    values = settings.get_all(db)
    if values["push.vapid_public"] and values["push.vapid_private"]:
        return False
    public, private = generate_vapid_keys()
    settings.set_values(db, {"push.vapid_public": public, "push.vapid_private": private})
    dropped = db.query(models.PushSubscription).delete()
    db.commit()
    logger.info(f"Push keys created{f' ({dropped} old devices dropped)' if dropped else ''}")
    return True


# ── delivery ────────────────────────────────────────────────
def _deliver(devices: list[tuple], payload: dict, private_pem: str, subject: str) -> tuple[int, list[int], int]:
    """Blocking. Returns (sent, ids of subscriptions that no longer exist, failures)."""
    vapid = Vapid.from_pem(private_pem.encode())
    data = json.dumps(payload)
    sent, gone, failed = 0, [], 0
    for device_id, endpoint, p256dh, auth in devices:
        try:
            webpush(
                {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=data,
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                ttl=TTL_SECONDS,
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                gone.append(device_id)
            else:
                failed += 1
                logger.warning(f"Push to device {device_id} failed: {e}")
        except Exception as e:
            failed += 1
            logger.warning(f"Push to device {device_id} failed: {e}")
    return sent, gone, failed


def active_users_only(query):
    """Devices of accounts that are still active: a disabled user gets no notices."""
    active = select(models.User.id).where(models.User.is_active == 1)
    return query.filter(models.PushSubscription.user_id.in_(active))


async def _send(query_filter, payload: dict) -> tuple[int, int]:
    """Send `payload` to the subscriptions selected by `query_filter(query)`; returns (sent, failed)."""
    with SessionLocal() as db:
        rows = active_users_only(query_filter(db.query(models.PushSubscription))).all()
        devices = [(r.id, r.endpoint, r.p256dh, r.auth) for r in rows]
    if not devices:
        return 0, 0
    sent, gone, failed = await asyncio.to_thread(
        _deliver, devices, payload, settings.get("push.vapid_private"), contact()
    )
    if gone:
        with SessionLocal() as db:
            db.query(models.PushSubscription).filter(models.PushSubscription.id.in_(gone)).delete(synchronize_session=False)
            db.commit()
        logger.info(f"Removed {len(gone)} expired push subscriptions")
    return sent, failed


AUDIENCES = ("me", "user", "group", "all")


async def deliver(payload: dict, audience: str, user_id: int | None = None) -> tuple[int, int]:
    """Send a prepared payload to `audience`: one user's devices ("me"/"user" with `user_id`),
    the devices that want group notices ("group") or every device ("all"). Returns (sent, failed)."""
    if not is_ready():
        return 0, 0
    if audience in ("me", "user"):
        selector = lambda q: q.filter(models.PushSubscription.user_id == user_id)  # noqa: E731
    elif audience == "group":
        selector = lambda q: q.filter(models.PushSubscription.receive_group == True)  # noqa: E712,E731
    elif audience == "all":
        selector = lambda q: q  # noqa: E731
    else:
        raise ValueError("Destino desconocido")
    try:
        sent, failed = await _send(selector, payload)
        logger.info(f"Push announcement to {audience}: {sent} sent, {failed} failed")
        return sent, failed
    except Exception as e:
        logger.error(f"Push announcement to {audience} failed: {e}")
        return 0, 0


async def notify_group(message: str, tag: str | None = "group") -> None:
    """What goes to the Telegram group, for every device that wants group notices."""
    if not is_ready():
        return
    try:
        sent, failed = await _send(
            lambda q: q.filter(models.PushSubscription.receive_group == True),  # noqa: E712
            build_payload(message, tag=tag),
        )
        logger.info(f"Push to group: {sent} sent, {failed} failed")
    except Exception as e:
        logger.error(f"Push to group failed: {e}")


async def notify_everyone(message: str, tag: str | None = None) -> tuple[int, int]:
    """A notice for every subscribed device, whatever its group preference. Returns (sent, failed)."""
    if not is_ready():
        return 0, 0
    try:
        sent, failed = await _send(lambda q: q, build_payload(message, tag=tag))
        logger.info(f"Push to everyone: {sent} sent, {failed} failed")
        return sent, failed
    except Exception as e:
        logger.error(f"Push to everyone failed: {e}")
        return 0, 0


async def notify_user(user_id: int, message: str, tag: str | None = None) -> tuple[int, int]:
    """A private notice for one user, on all of their devices. Returns (sent, failed)."""
    if not is_ready():
        return 0, 0
    try:
        sent, failed = await _send(
            lambda q: q.filter(models.PushSubscription.user_id == user_id),
            build_payload(message, tag=tag),
        )
        logger.info(f"Push to user {user_id}: {sent} sent, {failed} failed")
        return sent, failed
    except Exception as e:
        logger.error(f"Push to user {user_id} failed: {e}")
        return 0, 0

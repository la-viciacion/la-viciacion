"""Web Push: notifications for the installed PWA (the second channel next to Telegram).

Everything is off until an admin generates the VAPID keys and enables `push.enabled`
in the panel. Nothing here may break the Telegram path: every public function
swallows its errors and only logs them.

- notify_group: a copy of what goes to the Telegram group, for every device that
  wants group notices.
- notify_user: a private notice for one user, on all of their devices.
- notify_timer / notify_timer_stopped: the pinned "timer running" notification of a user's
  devices, refreshed every few minutes by the scheduler (same tag, so each one replaces the last).

Payloads are short plain text (title, body, url, tag): how long messages and images
fit into a push is still to be designed, see docs/desarrollo/roadmap.md.
"""
import asyncio
import base64
import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

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
BODY_MAX = 250  # what the AI notices take (their prompts ask for about 250 characters)
ANNOUNCEMENT_BODY_MAX = 240
PAYLOAD_MAX_BYTES = 3500  # the Web Push limit is 4096 bytes once encrypted
TTL_SECONDS = 3600  # a notice that could not be delivered within the hour is stale
MAX_DEVICES_PER_USER = 10

INBOX_URL = "#/notifications"  # where a tap on any notice but the timer's opens: the app's notification inbox

TIMER_TAG = "timer"
TIMER_TTL_SECONDS = 600  # a refresh that arrives late is worse than none: the next one is due in 10 minutes or more


# ── payload ─────────────────────────────────────────────────
def plain_text(message: str) -> str:
    """Telegram Markdown to plain text; a link keeps its text and loses the address (neither push nor the inbox can show it)."""
    text = re.sub(r"\[((?:\\.|[^\]\\])*)\]\([^)\s]*\)", r"\1", str(message))
    text = re.sub(r"\\(.)", r"\1", text)
    return re.sub(r"[*_`]", "", text)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_payload(message: str, url: str = INBOX_URL, tag: str | None = None, title: str | None = None) -> dict:
    """First line becomes the title and the rest the body; a one-liner gets the app name as title. A tap opens the inbox.
    A given `title` (the kind of notice, for a text that has none of its own) leaves the whole message as the body."""
    lines = [line.strip() for line in plain_text(message).splitlines() if line.strip()]
    if title:
        return {"title": _shorten(title, TITLE_MAX), "body": _shorten(" · ".join(lines), BODY_MAX), "url": url, "tag": tag}
    if not lines:
        title, body = APP_NAME, ""
    elif len(lines) == 1:
        title, body = APP_NAME, lines[0]
    else:
        title, body = lines[0], " · ".join(lines[1:])
    return {"title": _shorten(title, TITLE_MAX), "body": _shorten(body, BODY_MAX), "url": url, "tag": tag}


RECAP_TAG = "recap"  # + the period: the group's and the private notice of a recap replace each other (one on screen), a month and a season do not


# The second line of the recap notice, by kind of recap (also the text of the link on Telegram)
RECAP_TEASERS = {"mensual": "Descubre cómo ha ido el mes", "anual": "Descubre cómo ha ido el año"}


def build_recap_payload(kind: str, period: str) -> dict:
    """"Your recap is ready": a tap opens the story of whoever taps. The monthly link names no period (the story opens on the
    month that has ended); the annual one does, because a bare story would open on a month, not on the season."""
    return {"title": _shorten(f"🎬 Ya está disponible el resumen {kind}", TITLE_MAX), "body": RECAP_TEASERS[kind], "url": recap_story_path(kind, period), "tag": f"{RECAP_TAG}-{period}"}


def recap_story_path(kind: str, period: str) -> str:
    """The in-app address a recap notice opens: the story, with the period only for an annual recap."""
    return "#/story" if kind == "mensual" else f"#/story/{period}"


def build_announcement(title: str, body: str | None = None, url: str | None = None, image: str | None = None) -> dict:
    """A notice written by an admin. Raises ValueError with a message for the panel if it cannot be sent.

    Plain text only (no Markdown or HTML). `url` is where a tap opens the app (a path or a #/ route of
    this site; the inbox when empty), `image` an https picture shown large on Android and desktop (iOS ignores it).
    """
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("El título es obligatorio")
    if len(title) > TITLE_MAX:
        raise ValueError(f"El título admite {TITLE_MAX} caracteres como máximo")
    if len(body) > ANNOUNCEMENT_BODY_MAX:
        raise ValueError(f"El mensaje admite {ANNOUNCEMENT_BODY_MAX} caracteres como máximo")
    url = (url or "").strip() or INBOX_URL
    if not re.fullmatch(r"(/(?!/)|#/)[\w\-./?=&%#]*", url):
        raise ValueError("El enlace debe ser una ruta de la app (por ejemplo / o #/profile)")
    image = (image or "").strip() or None
    if image and not re.fullmatch(r"https://[^\s]{4,480}", image):
        raise ValueError("La imagen debe ser una URL https")
    payload = {"title": title, "body": body, "url": url, "tag": None}
    if image:
        payload["image"] = image
    if len(json.dumps(payload, ensure_ascii=False).encode()) > PAYLOAD_MAX_BYTES:
        raise ValueError("El aviso es demasiado grande")
    return payload


# ── running-timer notification ──────────────────────────────
def elapsed_text(seconds: float) -> str:
    """"Timer iniciado" under a minute, then "5 min" or "1h 05min". Mirrored by sw.js (formatElapsed)."""
    minutes = max(0, int(seconds)) // 60
    if minutes < 1:
        return "Timer iniciado"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}min" if hours else f"{minutes} min"


def build_timer_payload(game_name: str, start_time: datetime.datetime, now: datetime.datetime) -> dict:
    """The pinned notification of a running timer. Both tapping it and its "Parar" button open the app, where the timer is stopped."""
    return {
        "title": _shorten(game_name, TITLE_MAX),
        "body": elapsed_text((now - start_time).total_seconds()),
        "url": "/",
        "tag": TIMER_TAG,
        "quiet": True,
        "pinned": True,
        "button": "Parar",
    }


def build_timer_stopped_payload(game_name: str, duration_seconds: int | None) -> dict:
    """Replaces the pinned notification once the timer is over (no longer pinned, no sound)."""
    elapsed = elapsed_text(duration_seconds or 0)
    body = "Timer parado" if elapsed == "Timer iniciado" else f"Timer parado · {elapsed}"
    return {"title": _shorten(game_name, TITLE_MAX), "body": body, "url": "/", "tag": TIMER_TAG, "quiet": True}


# ── keys and settings ───────────────────────────────────────
def generate_vapid_keys() -> tuple[str, str]:
    """(public key as base64url for the browser, private key as PEM)."""
    vapid = Vapid()
    vapid.generate_keys()
    public = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(public).rstrip(b"=").decode(), vapid.private_pem().decode()


def contact() -> str:
    """Contact the push services can use to reach the sender (mailto: or https: URL)."""
    configured = settings.get("push.contact")
    if configured:
        return configured
    if config.SMTP_EMAIL:
        return f"mailto:{config.SMTP_EMAIL}"
    # the push services accept a mailto: or an https URL as the sender's contact
    return config.PUBLIC_URL if config.PUBLIC_URL.startswith("https://") else "mailto:admin@localhost"


def current_origin() -> str:
    """Which deployment this is: ENVIRONMENT plus the public address. The devices subscribed to a key belong to the
    site that served the app, so keys carried over in a database copy must not be used from anywhere else."""
    return f"{config.ENVIRONMENT}|{config.PUBLIC_URL}"


def is_ready() -> bool:
    return bool(
        settings.get("push.enabled")
        and settings.get("push.vapid_public")
        and settings.get("push.vapid_private")
        and settings.get("push.vapid_origin") == current_origin()
    )


def ensure_vapid_keys(db) -> bool:
    """Create the server's VAPID keys on the first start (or when the stored ones cannot be read).

    There is one pair for the whole server, never one per user. If the private key is
    missing or unreadable (SECRET_KEY changed), the old public key is useless: new keys are
    made and every device is dropped, because it subscribed to the old ones.
    Keys made for another deployment (a production dump restored in dev) are left untouched and push stays off:
    the devices in that copy are real ones. Keys from before the origin was recorded are claimed only by production.
    Returns True if keys were created.
    """
    values = settings.get_all(db)
    if values["push.vapid_public"] and values["push.vapid_private"]:
        origin = values.get("push.vapid_origin")
        if origin is None and config.ENVIRONMENT == "production":
            settings.set_values(db, {"push.vapid_origin": current_origin()})
        elif origin != current_origin():
            logger.error(
                f"Push is off: its keys belong to {origin or 'an unknown deployment'}, this is {current_origin()}. "
                "Generate new keys from the admin panel (this drops the devices of this database)."
            )
        return False
    public, private = generate_vapid_keys()
    settings.set_values(db, {"push.vapid_public": public, "push.vapid_private": private, "push.vapid_origin": current_origin()})
    dropped = db.query(models.PushSubscription).delete()
    db.commit()
    logger.info(f"Push keys created{f' ({dropped} old devices dropped)' if dropped else ''}")
    return True


# ── which endpoints are push services ───────────────────────
# The endpoint of a subscription is an address the server will POST to, and the browser decides it. Only the push services
# the browsers use are accepted (Chrome, Edge, Brave, Opera and Samsung use Google's; Firefox, Mozilla's; Safari, Apple's;
# Edge on Windows, Microsoft's): anything else would be a way to make the server call a host of the subscriber's choosing.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


def is_push_endpoint(endpoint: str) -> bool:
    """Whether `endpoint` is an https address on one of the push services (the host itself or a subdomain of it)."""
    try:
        parts = urlsplit(endpoint)
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        return False
    return any(host == service or host.endswith("." + service) for service in PUSH_SERVICE_HOSTS)


# ── delivery ────────────────────────────────────────────────
DELIVERY_WORKERS = 8  # devices reached at once: a slow push service delays its own devices, not everybody's


def _deliver(devices: list[tuple], payload: dict, private_pem: str, subject: str, ttl: int = TTL_SECONDS) -> tuple[int, list[int], int]:
    """Blocking. Returns (sent, ids of subscriptions that no longer exist, failures)."""
    vapid = Vapid.from_pem(private_pem.encode())
    data = json.dumps(payload, ensure_ascii=False)  # UTF-8 as it travels: \u escapes would take 6 bytes per character, 12 per emoji

    def one(device: tuple) -> tuple[str, int]:
        """('sent' | 'gone' | 'failed', the device id)"""
        device_id, endpoint, p256dh, auth = device
        if not is_push_endpoint(endpoint):  # rows from before the check: never called
            logger.warning(f"Push to device {device_id} skipped: its address is not a push service")
            return "failed", device_id
        try:
            webpush(
                {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=data,
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                ttl=ttl,
                timeout=10,
            )
            return "sent", device_id
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                return "gone", device_id
            logger.warning(f"Push to device {device_id} failed: {e}")
        except Exception as e:
            logger.warning(f"Push to device {device_id} failed: {e}")
        return "failed", device_id

    with ThreadPoolExecutor(max_workers=min(DELIVERY_WORKERS, len(devices) or 1)) as pool:
        results = list(pool.map(one, devices))
    return (
        sum(1 for outcome, _ in results if outcome == "sent"),
        [device_id for outcome, device_id in results if outcome == "gone"],
        sum(1 for outcome, _ in results if outcome == "failed"),
    )


def active_users_only(query):
    """Devices of accounts that are still active: a disabled user gets no notices."""
    active = select(models.User.id).where(models.User.is_active == 1, models.not_god())
    return query.filter(models.PushSubscription.user_id.in_(active))


async def _send(query_filter, payload: dict, ttl: int = TTL_SECONDS) -> tuple[int, int]:
    """Send `payload` to the subscriptions selected by `query_filter(query)`; returns (sent, failed)."""
    with SessionLocal() as db:
        rows = active_users_only(query_filter(db.query(models.PushSubscription))).all()
        devices = [(r.id, r.endpoint, r.p256dh, r.auth) for r in rows]
    if not devices:
        return 0, 0
    sent, gone, failed = await asyncio.to_thread(
        _deliver, devices, payload, settings.get("push.vapid_private"), contact(), ttl
    )
    if gone:
        with SessionLocal() as db:
            db.query(models.PushSubscription).filter(models.PushSubscription.id.in_(gone)).delete(synchronize_session=False)
            db.commit()
        logger.info(f"Removed {len(gone)} expired push subscriptions")
    return sent, failed


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
        logger.error(f"Push announcement to {audience} failed: {e}", exc_info=True)
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
        logger.error(f"Push to group failed: {e}", exc_info=True)


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
        logger.error(f"Push to user {user_id} failed: {e}", exc_info=True)
        return 0, 0


async def notify_timer(user_id: int, game_name: str, start_time: datetime.datetime) -> None:
    """Show or refresh the pinned notification of a running timer on all of the user's devices."""
    if not is_ready():
        return
    try:
        payload = build_timer_payload(game_name, start_time, datetime.datetime.now())
        await _send(lambda q: q.filter(models.PushSubscription.user_id == user_id), payload, TIMER_TTL_SECONDS)
    except Exception as e:
        logger.error(f"Timer push to user {user_id} failed: {e}", exc_info=True)


async def notify_timer_stopped(user_id: int, game_name: str, duration_seconds: int | None) -> None:
    """Unpin the notification of a timer that is over, on all of the user's devices."""
    if not is_ready():
        return
    try:
        payload = build_timer_stopped_payload(game_name, duration_seconds)
        await _send(lambda q: q.filter(models.PushSubscription.user_id == user_id), payload)
    except Exception as e:
        logger.error(f"Timer-stopped push to user {user_id} failed: {e}", exc_info=True)

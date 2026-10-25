"""The notification inbox: a copy, per player, of the notices the app sends, so one that was missed (push off,
a cut-off notification) can be read later in the app.

- record_group: what goes to the Telegram group, for every active player.
- record_user: a private notice, for that player only.

Not recorded: the timer's own notifications (start, stop, forgotten-timer reminder), which only matter at the
moment, and anything sent silently or while the general notifications switch is off (the senders return first).
Like push, nothing here may break the Telegram path: errors are only logged.
"""
import datetime
import re

from sqlalchemy import delete, select, update

from ..database import models
from ..database.database import SessionLocal
from . import push, settings
from .logger import LogManager

logger = LogManager().get_logger()

BODY_MAX = 255

# A link to a game ([name](https://rawg.io/games/slug) or of its page in the app) in the Telegram text: the inbox keeps
# the ones in the body so the page can show them. Any other link (a recap's story) is not shown inside the notice.
LINK = re.compile(r"\[((?:\\.|[^\]\\])*)\]\((https?://(?:rawg\.io/games/|[^)\s]*/#/game/)[^)\s]*)\)")


def linked_body(message: str, body: str) -> str:
    """`body` (plain, as push shows it) with the links of `message` put back, as [text](url), where their text is
    found in it. When the markup does not fit the column the last links go back to plain text first."""
    spans = []
    cursor = 0
    for found in LINK.finditer(message):
        text = push.plain_text(found.group(1))
        start = body.find(text, cursor) if text else -1
        if start < 0:
            continue
        spans.append((start, start + len(text), found.group(2)))
        cursor = start + len(text)
    while spans:
        out, last = "", 0
        for start, end, url in spans:
            out += body[last:start] + f"[{body[start:end]}]({url})"
            last = end
        out += body[last:]
        if len(out) <= BODY_MAX:
            return out
        spans.pop()
    return body


def payload_of(message: str, push_payload: dict | None = None) -> dict:
    """The title, body and link the inbox shows: the push payload when the notice has its own, else the message as push shows it."""
    payload = push_payload or push.build_payload(message)
    body = (payload.get("body") or "")[:BODY_MAX]
    return {
        "title": payload["title"],
        "body": linked_body(message, body),
        # a notice that opens the inbox is not a link inside it
        "url": "/" if payload.get("url") in (None, "", push.INBOX_URL) else payload["url"],
    }


def _store(user_ids: list[int], payload: dict) -> int:
    if not user_ids:
        return 0
    with SessionLocal() as db:
        db.add_all(models.UserNotification(user_id=user_id, **payload) for user_id in user_ids)
        db.commit()
    return len(user_ids)


def record_group(message: str, push_payload: dict | None = None) -> None:
    """Add the notice to the inbox of every active player."""
    try:
        with SessionLocal() as db:
            user_ids = list(db.scalars(select(models.User.id).where(models.User.is_active == 1, models.not_god())))
        _store(user_ids, payload_of(message, push_payload))
    except Exception as e:
        logger.error(f"Inbox: could not record a group notice: {e}", exc_info=True)


def record_user(user_id: int, message: str, push_payload: dict | None = None) -> None:
    """Add the notice to one player's inbox."""
    try:
        _store([user_id], payload_of(message, push_payload))
    except Exception as e:
        logger.error(f"Inbox: could not record a notice for user {user_id}: {e}", exc_info=True)


def record_audience(audience: str, user_id: int, payload: dict) -> None:
    """An admin's notice, by the audience the composer chose ("me", "user", "group" or "all"): the group and everybody
    mean every active player here, since the inbox has no devices to pick from."""
    if audience in ("group", "all"):
        record_group("", payload)
    else:
        record_user(user_id, "", payload)


def purge(db, now: datetime.datetime | None = None) -> int:
    """Delete the notices older than the retention setting. Returns how many."""
    days = settings.get("inbox.retention_days")
    limit = (now or datetime.datetime.now()) - datetime.timedelta(days=days)
    deleted = db.execute(delete(models.UserNotification).where(models.UserNotification.created_at < limit)).rowcount
    db.commit()
    return deleted


def mark_all_read(db, user_id: int, now: datetime.datetime | None = None) -> None:
    db.execute(
        update(models.UserNotification)
        .where(models.UserNotification.user_id == user_id, models.UserNotification.read_at.is_(None))
        .values(read_at=now or datetime.datetime.now())
    )
    db.commit()

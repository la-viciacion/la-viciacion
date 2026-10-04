"""Audit log of the admin panel: who changed what, and how it was before.

Every write (POST, PUT, PATCH, DELETE) of `routers/manage.py` that succeeds leaves one row in `audit_log`. It
is done once, for the whole router, instead of in every handler: a handler added tomorrow is covered without
anybody remembering to log it (tests/test_audit.py fails a /manage route that is not).

Two pieces cooperate. `remember` is a router dependency that runs after `require_admin` (so nothing is read or
queried for a caller who is not an admin): it keeps the actor, the JSON body and, for an edit or a delete of a
known row, how that row was before. `AuditedRoute` then writes the row once the handler has answered with a
success. A failed request changed nothing, so it leaves no trace; a failure to write the log never fails the request.

What is stored is for people to read: passwords, tokens and keys are replaced by `***`, long texts are cut, and
the pictures of a user or an achievement are left out.
"""
import datetime
import json
import re
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute

from .. import auth
from ..database import models
from ..database.database import SessionLocal
from .logger import LogManager

logger = LogManager().get_logger()

READ_ONLY = frozenset({"GET", "HEAD", "OPTIONS"})
SENSITIVE = re.compile(r"pass|token|secret|api_key|private", re.IGNORECASE)
HIDDEN = "***"
TEXT_MAX = 300
LIST_MAX = 50
DETAIL_MAX = 8000

# first path segment under /manage -> (model, type of its id): the rows whose previous state is kept
SNAPSHOTS = {
    "users": (models.User, int),
    "games": (models.Game, str),
    "platforms": (models.PlatformTag, str),
    "timers": (models.GameTimer, int),
    "library": (models.UserGame, int),
    "scores": (models.GameScore, int),
    "achievements": (models.Achievement, int),
    "user-achievements": (models.UserAchievement, int),
}
# never copied into the log: secrets, and pictures that would only make it heavy
SKIPPED_COLUMNS = {"password", "avatar", "image"}


def redact(value, key: str = ""):
    """The value as it may be stored: secrets hidden, texts and lists cut."""
    if key and SENSITIVE.search(key):
        return HIDDEN
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value[:LIST_MAX]]
    if isinstance(value, str) and len(value) > TEXT_MAX:
        return value[:TEXT_MAX] + "…"
    return value


def target_of(path: str) -> tuple[str | None, str | None]:
    """(entity, id) of a /manage path: `/api/v1/manage/timers/12` -> ("timers", "12"). The id is only
    given for the entities whose rows are kept in the log."""
    _, _, rest = path.partition("/manage/")
    parts = [p for p in rest.split("/") if p]
    if not parts:
        return None, None
    entity = parts[0]
    return entity, parts[1] if entity in SNAPSHOTS and len(parts) > 1 else None


def snapshot(db, entity: str | None, entity_id: str | None) -> dict | None:
    """How a row was before an edit or a delete (without secrets and pictures), None if there is none."""
    if entity not in SNAPSHOTS or entity_id is None:
        return None
    model, kind = SNAPSHOTS[entity]
    try:
        row = db.get(model, kind(entity_id))
    except ValueError:
        return None
    if row is None:
        return None
    columns = [c.key for c in model.__table__.columns if c.key not in SKIPPED_COLUMNS]
    return redact({c: _plain(getattr(row, c)) for c in columns})


def _plain(value):
    return value.isoformat() if isinstance(value, (datetime.date, datetime.datetime)) else value


def detail_json(body, before, query: str) -> str | None:
    """The `detail` column: what was sent (`body`), what there was (`before`) and the query string."""
    detail = {}
    if before is not None:
        detail["before"] = before
    if body not in (None, {}):
        detail["body"] = redact(body)
    if query:
        detail["query"] = query
    if not detail:
        return None
    text = json.dumps(detail, ensure_ascii=False, default=str)
    if len(text) > DETAIL_MAX:
        text = json.dumps({"truncated": text[:DETAIL_MAX]}, ensure_ascii=False)
    return text


def entry_out(row: models.AuditLog) -> dict:
    """A row of the log as the admin panel lists it (`detail` as an object, not as text)."""
    try:
        detail = json.loads(row.detail) if row.detail else None
    except ValueError:
        detail = None
    return {
        "id": row.id,
        "created_at": row.created_at,
        "user_id": row.user_id,
        "username": row.username,
        "method": row.method,
        "path": row.path,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "status": row.status,
        "detail": detail,
    }


@dataclass
class Pending:
    """What `remember` keeps about a request until it is known to have succeeded."""

    user_id: int
    username: str
    body: object
    before: dict | None


def _read_snapshot(entity, entity_id):
    """Best effort, like the rest of the log: not being able to tell how a row was must not stop the change."""
    try:
        with SessionLocal() as db:
            return snapshot(db, entity, entity_id)
    except Exception as e:
        logger.error("Error reading a row for the audit log: " + str(e))
        return None


async def _json_body(request: Request):
    if "json" not in request.headers.get("content-type", ""):
        return None
    try:
        return json.loads(await request.body())  # cached: the handler still reads it
    except ValueError:
        return None


async def remember(request: Request, admin: models.User = Depends(auth.require_admin)):
    """Router dependency: keep what the audit row will need, before the handler changes anything."""
    if request.method in READ_ONLY:
        return
    entity, entity_id = target_of(request.url.path)
    before = await run_in_threadpool(_read_snapshot, entity, entity_id) if request.method != "POST" else None
    request.state.audit = Pending(admin.id, admin.username, await _json_body(request), before)


def _created_id(response) -> str | None:
    try:
        data = json.loads(getattr(response, "body", b"") or b"null")
    except ValueError:
        return None
    return str(data["id"]) if isinstance(data, dict) and data.get("id") is not None else None


def write(pending: Pending, request: Request, status: int, created_id: str | None) -> None:
    """Add the row. Never raises: the change it describes is already made."""
    entity, entity_id = target_of(request.url.path)
    try:
        with SessionLocal() as db:
            db.add(models.AuditLog(
                user_id=pending.user_id,
                username=pending.username,
                method=request.method,
                path=request.url.path[:255],
                entity=entity,
                entity_id=entity_id or created_id,
                status=status,
                detail=detail_json(pending.body, pending.before, request.url.query),
            ))
            db.commit()
    except Exception as e:
        logger.error("Error writing the audit log: " + str(e))


class AuditedRoute(APIRoute):
    """Writes the audit row of a successful request that `remember` has seen."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def audited(request: Request):
            response = await handler(request)
            pending = getattr(request.state, "audit", None)
            if pending is not None and response.status_code < 400:
                await run_in_threadpool(write, pending, request, response.status_code, _created_id(response))
            return response

        return audited

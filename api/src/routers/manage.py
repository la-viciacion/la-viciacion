"""Admin panel API: data management for users, games, sessions, library and
achievements. Every route requires an admin (router-level dependency).

Deletes of records that other data hangs from are refused with a 409 that
lists what would be lost, unless `force=true` is passed - the panel shows that
list to the admin and re-sends with force after an explicit confirmation.
"""
import datetime
import re
import unicodedata
from typing import Optional

from bcrypt import gensalt, hashpw
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import users as users_crud
from ..database import models
from ..utils import actions, ai, my_utils, push, rawg_sync, seasons, settings
from ..utils import email as mail
from ..database.schemas import NOTES_MAX
from ..utils.logger import LogManager
from ..utils.my_utils import normalize_email, validate_email_format, validate_password_requirements, validate_username

logger = LogManager().get_logger()

router = APIRouter(
    prefix="/manage",
    tags=["Manage"],
    dependencies=[Depends(auth.require_admin)],
)


def _commit(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{what}: conflicto con un registro existente")


def _get_or_404(db: Session, model, key, what: str):
    row = db.get(model, key)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} no encontrado")
    return row


def _confirm_or_409(counts: dict, force: bool):
    """Refuse to delete something with dependants unless the admin forced it."""
    counts = {k: v for k, v in counts.items() if v}
    if counts and not force:
        raise HTTPException(status_code=409, detail={"message": "Tiene datos asociados", "counts": counts})


def _sorted(query, column, order: str, tie_breaker):
    """ORDER BY `column` (asc/desc); the id keeps pages stable when values repeat."""
    direction = column.desc() if order == "desc" else column.asc()
    return query.order_by(direction, tie_breaker.desc() if order == "desc" else tie_breaker.asc())


def _like(term: str) -> str:
    return "%" + term.replace("%", r"\%").replace("_", r"\_") + "%"


# ── Overview ────────────────────────────────────────────────────


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return {
        "users": db.query(func.count(models.User.id)).scalar(),
        "games": db.query(func.count(models.Game.id)).scalar(),
        "timers": db.query(func.count(models.GameTimer.id)).scalar(),
        "active_timers": db.query(func.count(models.GameTimer.id))
        .filter(models.GameTimer.is_active == True)  # noqa: E712
        .scalar(),
        "library": db.query(func.count(models.UserGame.id)).scalar(),
    }


# A timer left running this long is almost surely forgotten (the hourly job only nudges its owner).
STALE_TIMER_HOURS = 12


@router.get("/attention")
def attention(db: Session = Depends(get_db)):
    """What the admin may want to look at: forgotten timers, players the bot cannot reach and
    games without RAWG metadata. Computed on request, like every other figure."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=STALE_TIMER_HOURS)
    stale = (
        db.query(models.GameTimer)
        .filter(models.GameTimer.is_active == True, models.GameTimer.start_time < cutoff)  # noqa: E712
    )
    oldest = (
        stale.join(models.User, models.User.id == models.GameTimer.user_id)
        .join(models.Game, models.Game.id == models.GameTimer.game_id)
        .with_entities(models.User.username, models.Game.name, models.GameTimer.start_time)
        .order_by(models.GameTimer.start_time)
        .limit(5)
        .all()
    )
    return {
        "stale_timer_hours": STALE_TIMER_HOURS,
        "stale_timers": stale.count(),
        "stale_timers_oldest": [{"user": u, "game": g, "start_time": s.isoformat()} for u, g, s in oldest],
        "users_without_telegram": db.query(func.count(models.User.id))
        .filter(models.User.is_active == 1, models.User.telegram_id.is_(None), models.not_god())
        .scalar(),
        "games_without_rawg": db.query(func.count(models.Game.id)).filter(models.Game.rawg_id.is_(None)).scalar(),
    }


class CheckAchievementsBody(BaseModel):
    user_id: Optional[int] = None
    silent: bool = True


@router.post("/check-achievements", status_code=202)
def check_achievements(body: CheckAchievementsBody, background_tasks: BackgroundTasks):
    """Check the achievements of all users, or one, against their sessions (in background)."""
    background_tasks.add_task(actions.after_session_change, body.user_id, body.silent)
    return {"message": "Comprobación en marcha"}


# ── Users ───────────────────────────────────────────────────────


def _user_out(u: models.User, sessions: int = 0, library: int = 0) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "username": u.username,
        "email": u.email,
        "telegram_id": u.telegram_id,
        "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active),
        "sessions": sessions,
        "library": library,
    }


@router.get("/users")
def list_users(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.User)
    if search:
        t = _like(search)
        q = q.filter(or_(models.User.username.like(t), models.User.name.like(t), models.User.email.like(t)))
    total = q.count()
    users = q.order_by(models.User.username).limit(limit).offset(offset).all()
    ids = [u.id for u in users]
    sessions = dict(
        db.query(models.GameTimer.user_id, func.count(models.GameTimer.id))
        .filter(models.GameTimer.user_id.in_(ids))
        .group_by(models.GameTimer.user_id)
        .all()
    )
    library = dict(
        db.query(models.UserGame.user_id, func.count(models.UserGame.id))
        .filter(models.UserGame.user_id.in_(ids))
        .group_by(models.UserGame.user_id)
        .all()
    )
    return {"total": total, "items": [_user_out(u, sessions.get(u.id, 0), library.get(u.id, 0)) for u in users]}


def _checked_email(db: Session, email, *, exclude_user_id=None):
    """Normalized email that is valid and free: it is the login identifier, so it is required."""
    email = normalize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="El email es obligatorio")
    if not validate_email_format(email):
        raise HTTPException(status_code=400, detail="El email no es válido")
    if users_crud.email_in_use(db, email, exclude_user_id=exclude_user_id):
        raise HTTPException(status_code=409, detail="Ese email ya está en uso por otra cuenta")
    return email


def _check_username(db: Session, username: str, *, exclude_user_id=None):
    error = validate_username(username)
    if error:
        raise HTTPException(status_code=400, detail=error)
    other = users_crud.get_user_by_username(db, username)
    if other and other.id != exclude_user_id:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe")


def _check_telegram_id(db: Session, telegram_id, *, exclude_user_id=None):
    if telegram_id is not None and users_crud.telegram_id_in_use(db, telegram_id, exclude_user_id=exclude_user_id):
        raise HTTPException(status_code=409, detail="Ese ID de Telegram ya está en uso por otra cuenta")


class UserCreateBody(BaseModel):
    email: str
    username: str
    name: Optional[str] = None
    telegram_id: Optional[int] = None
    password: str
    is_admin: bool = False
    is_active: bool = True


@router.post("/users", status_code=201)
def create_user(body: UserCreateBody, db: Session = Depends(get_db)):
    """Create an account (the only way to add users for now)."""
    email = _checked_email(db, body.email)
    username = body.username.strip()
    _check_username(db, username)
    _check_telegram_id(db, body.telegram_id)
    if not validate_password_requirements(body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener 12-24 caracteres, mayúscula, minúscula, número y un carácter especial",
        )
    try:
        user = users_crud.insert_user(
            db,
            username=username,
            email=email,
            name=(body.name or "").strip() or None,
            password=body.password,
            is_admin=body.is_admin,
            is_active=body.is_active,
            telegram_id=body.telegram_id,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Ese email o usuario ya existe")
    return _user_out(user)


class UserPatch(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int,
    body: UserPatch,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_or_404(db, models.User, user_id, "Usuario")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("is_admin") is False or data.get("is_active") is False):
        raise HTTPException(status_code=400, detail="No puedes quitarte el rol de admin ni desactivarte a ti mismo")
    if data.get("telegram_id") is not None:
        _check_telegram_id(db, data["telegram_id"], exclude_user_id=user.id)
    if "name" in data:
        # never empty: messages and rankings print it (falls back to the nickname)
        data["name"] = (data["name"] or "").strip() or (data.get("username") or user.username).strip()
    if "email" in data:
        data["email"] = _checked_email(db, data["email"], exclude_user_id=user.id)
    if data.get("username") is not None:
        data["username"] = data["username"].strip()
        _check_username(db, data["username"], exclude_user_id=user.id)
    for field in ("is_admin", "is_active"):
        if field in data and data[field] is not None:
            data[field] = int(data[field])
    for k, v in data.items():
        setattr(user, k, v)
    _commit(db, "Usuario")
    return _user_out(user)


class PasswordBody(BaseModel):
    password: str


@router.post("/users/{user_id}/password")
def set_password(user_id: int, body: PasswordBody, db: Session = Depends(get_db)):
    user = _get_or_404(db, models.User, user_id, "Usuario")
    if not validate_password_requirements(body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener 12-24 caracteres, mayúscula, minúscula, número y un carácter especial",
        )
    user.password = hashpw(body.password.encode("utf-8"), gensalt()).decode()
    db.commit()
    return {"message": "Contraseña actualizada"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    force: bool = False,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_or_404(db, models.User, user_id, "Usuario")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes borrarte a ti mismo")
    counts = {
        "sesiones": db.query(models.GameTimer).filter_by(user_id=user_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(user_id=user_id).count(),
        "logros": db.query(models.UserAchievement).filter_by(user_id=user_id).count(),
    }
    _confirm_or_409(counts, force)
    db.query(models.GameTimer).filter_by(user_id=user_id).delete()
    db.query(models.UserGame).filter_by(user_id=user_id).delete()
    db.query(models.UserAchievement).filter_by(user_id=user_id).delete()
    db.query(models.PushSubscription).filter_by(user_id=user_id).delete()
    db.delete(user)
    db.commit()
    return {"message": "Usuario eliminado"}


# ── Games ───────────────────────────────────────────────────────


class GamePatch(BaseModel):
    name: Optional[str] = None
    dev: Optional[str] = None
    release_date: Optional[datetime.date] = None
    steam_id: Optional[str] = None
    image_url: Optional[str] = None
    genres: Optional[str] = None
    avg_time: Optional[int] = None
    slug: Optional[str] = None
    rawg_id: Optional[int] = None


def _game_out(g: models.Game, sessions: int = 0, players: int = 0) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "dev": g.dev,
        "release_date": g.release_date,
        "steam_id": g.steam_id,
        "image_url": g.image_url,
        "genres": g.genres,
        "avg_time": g.avg_time,
        "slug": g.slug,
        "rawg_id": g.rawg_id,
        "sessions": sessions,
        "players": players,
    }


@router.get("/games")
def list_games(
    search: Optional[str] = None,
    rawg: Optional[str] = Query(None, pattern="^(linked|unlinked)$"),
    usage: Optional[str] = Query(None, pattern="^(used|unused)$"),
    sort: str = Query("name", pattern="^(name|release_date|sessions|players)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Games with their usage. Filters: linked to RAWG, used (has sessions or players)."""
    session_counts = (
        db.query(models.GameTimer.game_id.label("gid"), func.count(models.GameTimer.id).label("n"))
        .group_by(models.GameTimer.game_id)
        .subquery()
    )
    player_counts = (
        db.query(models.UserGame.game_id.label("gid"), func.count(func.distinct(models.UserGame.user_id)).label("n"))
        .group_by(models.UserGame.game_id)
        .subquery()
    )
    sessions = func.coalesce(session_counts.c.n, 0)
    players = func.coalesce(player_counts.c.n, 0)
    q = (
        db.query(models.Game, sessions.label("sessions"), players.label("players"))
        .outerjoin(session_counts, session_counts.c.gid == models.Game.id)
        .outerjoin(player_counts, player_counts.c.gid == models.Game.id)
    )
    if search:
        q = q.filter(models.Game.name.like(_like(search)))
    if rawg:
        q = q.filter(models.Game.rawg_id.isnot(None) if rawg == "linked" else models.Game.rawg_id.is_(None))
    if usage:
        in_use = (sessions > 0) | (players > 0)
        q = q.filter(in_use if usage == "used" else ~in_use)
    total = q.count()
    column = {"name": models.Game.name, "release_date": models.Game.release_date, "sessions": sessions, "players": players}[sort]
    direction = column.desc() if order == "desc" else column.asc()
    rows = q.order_by(direction, models.Game.name, models.Game.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_game_out(g, s, p) for g, s, p in rows]}


@router.patch("/games/{game_id}")
def patch_game(game_id: str, body: GamePatch, db: Session = Depends(get_db)):
    game = _get_or_404(db, models.Game, game_id, "Juego")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    for k, v in data.items():
        setattr(game, k, v)
    _commit(db, "Juego")
    return _game_out(game)


def _game_counts(db: Session, game_id: str) -> dict:
    return {
        "sesiones": db.query(models.GameTimer).filter_by(game_id=game_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(game_id=game_id).count(),
        "logros": db.query(models.UserAchievement).filter_by(game_id=game_id).count(),
    }


@router.delete("/games/{game_id}")
def delete_game(game_id: str, force: bool = False, db: Session = Depends(get_db)):
    game = _get_or_404(db, models.Game, game_id, "Juego")
    _confirm_or_409(_game_counts(db, game_id), force)
    db.query(models.GameTimer).filter_by(game_id=game_id).delete()
    db.query(models.UserGame).filter_by(game_id=game_id).delete()
    db.query(models.UserAchievement).filter_by(game_id=game_id).delete()
    db.delete(game)
    db.commit()
    return {"message": "Juego eliminado"}


# ── RAWG sync (intensive: consumes the monthly RAWG quota) ──────

RAWG_SYNC_PHRASE = "SINCRONIZAR"


@router.get("/rawg-sync/estimate")
def rawg_sync_estimate(overwrite: bool = False, db: Session = Depends(get_db)):
    """How many games/calls a sync would take. Makes no RAWG request."""
    return rawg_sync.estimate(db, overwrite)


@router.get("/rawg-sync/status")
def rawg_sync_status():
    return rawg_sync.status()


class RawgSyncBody(BaseModel):
    confirm: str                       # must equal RAWG_SYNC_PHRASE (the panel asks for it twice)
    max_calls: int = 2000
    overwrite: bool = False


@router.post("/rawg-sync/start", status_code=202)
def rawg_sync_start(body: RawgSyncBody):
    if body.confirm != RAWG_SYNC_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmación incorrecta")
    if not 1 <= body.max_calls <= 20000:
        raise HTTPException(status_code=400, detail="max_calls debe estar entre 1 y 20000")
    try:
        started = rawg_sync.start(body.max_calls, body.overwrite)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not started:
        raise HTTPException(status_code=409, detail="Ya hay una sincronización en curso")
    return rawg_sync.status()


@router.post("/rawg-sync/cancel")
def rawg_sync_cancel():
    return {"cancelling": rawg_sync.cancel()}


class RawgApplyBody(BaseModel):
    game_id: str
    rawg_id: int
    overwrite: bool = False


@router.post("/rawg-sync/apply")
def rawg_sync_apply(body: RawgApplyBody, db: Session = Depends(get_db)):
    """Resolve an ambiguous game by choosing its RAWG entry (1-2 RAWG calls)."""
    try:
        return rawg_sync.apply_one(db, body.game_id, body.rawg_id, body.overwrite)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ConnectionError, rawg_sync.RawgFatal) as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Sessions (game_timers) ──────────────────────────────────────


def _timer_out(t: models.GameTimer, user_name: Optional[str], game_name: Optional[str]) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "user": user_name,
        "game_id": t.game_id,
        "game": game_name,
        "start_time": t.start_time,
        "end_time": t.end_time,
        "duration_seconds": t.duration_seconds,
        "platform": t.platform,
        "season": t.season,
        "is_active": bool(t.is_active),
        "notes": t.notes,
    }


@router.get("/timers")
def list_timers(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    active: Optional[bool] = None,
    season: Optional[int] = None,
    platform: Optional[str] = None,
    sort: str = Query("start", pattern="^(user|game|start|end|duration|platform|season)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.GameTimer, models.User.username, models.Game.name)
        .outerjoin(models.User, models.User.id == models.GameTimer.user_id)
        .outerjoin(models.Game, models.Game.id == models.GameTimer.game_id)
    )
    if user_id is not None:
        q = q.filter(models.GameTimer.user_id == user_id)
    if game_id:
        q = q.filter(models.GameTimer.game_id == game_id)
    if active is not None:
        q = q.filter(models.GameTimer.is_active == active)
    if season is not None:
        q = q.filter(models.GameTimer.season == season)
    if platform:
        q = q.filter(models.GameTimer.platform == platform)
    total = q.count()
    columns = {
        "user": models.User.username,
        "game": models.Game.name,
        "start": models.GameTimer.start_time,
        "end": models.GameTimer.end_time,
        "duration": models.GameTimer.duration_seconds,
        "platform": models.GameTimer.platform,
        "season": models.GameTimer.season,
    }
    rows = _sorted(q, columns[sort], order, models.GameTimer.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_timer_out(t, u, g) for t, u, g in rows]}


class TimerCreate(BaseModel):
    user_id: int
    game_id: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    platform: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_MAX)


def _check_range(start: datetime.datetime, end: Optional[datetime.datetime]):
    if end is not None and end <= start:
        raise HTTPException(status_code=400, detail="El fin debe ser posterior al inicio")


@router.post("/timers", status_code=201)
def create_timer(body: TimerCreate, db: Session = Depends(get_db)):
    """Create a finished session by hand (e.g. a forgotten timer)."""
    _get_or_404(db, models.User, body.user_id, "Usuario")
    _get_or_404(db, models.Game, body.game_id, "Juego")
    _check_range(body.start_time, body.end_time)
    timer = models.GameTimer(
        user_id=body.user_id,
        game_id=body.game_id,
        start_time=body.start_time,
        end_time=body.end_time,
        duration_seconds=int((body.end_time - body.start_time).total_seconds()),
        platform=body.platform,
        is_active=False,
        notes=body.notes,
    )
    db.add(timer)
    users_crud.ensure_library_entry(db, body.user_id, body.game_id, body.platform, body.start_time)
    _commit(db, "Sesión")
    return _timer_out(timer, None, None)


class TimerPatch(BaseModel):
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    platform: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_MAX)


@router.patch("/timers/{timer_id}")
def patch_timer(timer_id: int, body: TimerPatch, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Edit a session. Setting an end time finishes an active one (stuck timer)."""
    timer = _get_or_404(db, models.GameTimer, timer_id, "Sesión")
    was_running = bool(timer.is_active)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(timer, k, v)
    _check_range(timer.start_time, timer.end_time)
    if timer.end_time is not None:
        timer.duration_seconds = int((timer.end_time - timer.start_time).total_seconds())
        timer.is_active = False
    _commit(db, "Sesión")
    if was_running and not timer.is_active:
        # a stuck timer was finished by hand: its pinned notification has to go
        background_tasks.add_task(actions.after_timer_stop, timer.user_id, timer.game_id, timer.duration_seconds)
    return _timer_out(timer, None, None)


@router.delete("/timers/{timer_id}")
def delete_timer(timer_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    timer = _get_or_404(db, models.GameTimer, timer_id, "Sesión")
    if timer.is_active:
        background_tasks.add_task(actions.after_timer_stop, timer.user_id, timer.game_id, None)
    db.delete(timer)
    db.commit()
    return {"message": "Sesión eliminada"}


# ── Library (users_games) ───────────────────────────────────────


def _library_out(u: models.UserGame, user_name: Optional[str], game_name: Optional[str]) -> dict:
    return {
        "id": u.id,
        "user_id": u.user_id,
        "user": user_name,
        "game_id": u.game_id,
        "game": game_name,
        "platform": u.platform,
        "season": u.season,
        "started_date": u.started_date,
        "completed": bool(u.completed),
        "completed_date": u.completed_date,
        "score": u.score,
    }


@router.get("/library")
def list_library(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    season: Optional[int] = None,
    platform: Optional[str] = None,
    completed: Optional[str] = Query(None, pattern="^(yes|no)$"),
    sort: str = Query("season", pattern="^(user|game|platform|season|started|completed|score)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.UserGame, models.User.username, models.Game.name)
        .outerjoin(models.User, models.User.id == models.UserGame.user_id)
        .outerjoin(models.Game, models.Game.id == models.UserGame.game_id)
    )
    if user_id is not None:
        q = q.filter(models.UserGame.user_id == user_id)
    if game_id:
        q = q.filter(models.UserGame.game_id == game_id)
    if season is not None:
        q = q.filter(models.UserGame.season == season)
    if platform:
        q = q.filter(models.UserGame.platform == platform)
    if completed:
        q = q.filter(models.UserGame.completed == 1 if completed == "yes" else func.coalesce(models.UserGame.completed, 0) == 0)
    total = q.count()
    columns = {
        "user": models.User.username,
        "game": models.Game.name,
        "platform": models.UserGame.platform,
        "season": models.UserGame.season,
        "started": models.UserGame.started_date,
        "completed": models.UserGame.completed_date,
        "score": models.UserGame.score,
    }
    rows = _sorted(q, columns[sort], order, models.UserGame.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_library_out(u, un, gn) for u, un, gn in rows]}


class LibraryCreate(BaseModel):
    user_id: int
    game_id: str
    platform: Optional[str] = None
    started_date: Optional[datetime.date] = None  # its year is the entry's season (default: today)


@router.post("/library", status_code=201)
def create_library(body: LibraryCreate, db: Session = Depends(get_db)):
    _get_or_404(db, models.User, body.user_id, "Usuario")
    _get_or_404(db, models.Game, body.game_id, "Juego")
    row = models.UserGame(
        user_id=body.user_id,
        game_id=body.game_id,
        platform=body.platform,
        completed=0,
        started_date=body.started_date or datetime.date.today(),
    )
    db.add(row)
    _commit(db, "Biblioteca")
    return _library_out(row, None, None)


class LibraryPatch(BaseModel):
    platform: Optional[str] = None
    started_date: Optional[datetime.date] = None
    completed: Optional[bool] = None
    completed_date: Optional[datetime.date] = None
    score: Optional[float] = None


@router.patch("/library/{row_id}")
def patch_library(row_id: int, body: LibraryPatch, db: Session = Depends(get_db)):
    row = _get_or_404(db, models.UserGame, row_id, "Entrada de biblioteca")
    data = body.model_dump(exclude_unset=True)
    if data.get("score") is not None and not (0 <= data["score"] <= 10):
        raise HTTPException(status_code=400, detail="La nota debe estar entre 0 y 10")
    if "completed" in data and data["completed"] is not None:
        data["completed"] = int(data["completed"])
    for k, v in data.items():
        setattr(row, k, v)
    _commit(db, "Biblioteca")
    return _library_out(row, None, None)


@router.delete("/library/{row_id}")
def delete_library(row_id: int, db: Session = Depends(get_db)):
    row = _get_or_404(db, models.UserGame, row_id, "Entrada de biblioteca")
    db.delete(row)
    db.commit()
    return {"message": "Entrada eliminada"}


# ── Platforms (platform_tags) ───────────────────────────────────


PLATFORM_NAME_MAX = 100


def platform_id_for(name: str, taken: set) -> str:
    """A readable, url-safe id for a new platform ("PlayStation 5" -> "playstation-5"), unique among `taken`."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60] or "platform"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _platform_out(p: models.PlatformTag, sessions: int = 0, library: int = 0) -> dict:
    return {"id": p.id, "name": p.name, "sessions": sessions, "library": library}


def _platform_usage(db: Session, platform_id: str) -> dict:
    return {
        "sesiones": db.query(models.GameTimer).filter_by(platform=platform_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(platform=platform_id).count(),
    }


def _clean_platform_name(db: Session, name: str, exclude_id: Optional[str] = None) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    if len(name) > PLATFORM_NAME_MAX:
        raise HTTPException(status_code=400, detail=f"El nombre admite {PLATFORM_NAME_MAX} caracteres como máximo")
    same = db.query(models.PlatformTag).filter(func.lower(models.PlatformTag.name) == name.lower())
    if exclude_id is not None:
        same = same.filter(models.PlatformTag.id != exclude_id)
    if same.first() is not None:
        raise HTTPException(status_code=409, detail="Ya hay una plataforma con ese nombre")
    return name


class PlatformBody(BaseModel):
    name: str


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db)):
    """Every platform with how many sessions and library entries use it."""
    sessions = dict(
        db.query(models.GameTimer.platform, func.count(models.GameTimer.id))
        .filter(models.GameTimer.platform.isnot(None))
        .group_by(models.GameTimer.platform)
        .all()
    )
    library = dict(
        db.query(models.UserGame.platform, func.count(models.UserGame.id))
        .filter(models.UserGame.platform.isnot(None))
        .group_by(models.UserGame.platform)
        .all()
    )
    platforms = db.query(models.PlatformTag).order_by(models.PlatformTag.name).all()
    return [_platform_out(p, sessions.get(p.id, 0), library.get(p.id, 0)) for p in platforms]


@router.post("/platforms", status_code=201)
def create_platform(body: PlatformBody, db: Session = Depends(get_db)):
    """Add a platform; its id is made from the name and never changes afterwards."""
    name = _clean_platform_name(db, body.name)
    taken = {row[0] for row in db.query(models.PlatformTag.id).all()}
    platform = models.PlatformTag(id=platform_id_for(name, taken), name=name)
    db.add(platform)
    _commit(db, "Plataforma")
    return _platform_out(platform)


@router.patch("/platforms/{platform_id}")
def patch_platform(platform_id: str, body: PlatformBody, db: Session = Depends(get_db)):
    """Rename a platform: sessions and library entries keep pointing at it by id."""
    platform = _get_or_404(db, models.PlatformTag, platform_id, "Plataforma")
    platform.name = _clean_platform_name(db, body.name, exclude_id=platform_id)
    _commit(db, "Plataforma")
    return _platform_out(platform)


@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id: str, db: Session = Depends(get_db)):
    """Delete a platform nobody uses. One that still has sessions or library entries is refused:
    deleting it would leave them without a platform, so rename it or change those first."""
    platform = _get_or_404(db, models.PlatformTag, platform_id, "Plataforma")
    usage = {k: v for k, v in _platform_usage(db, platform_id).items() if v}
    if usage:
        detail = " y ".join(f"{v} {k}" for k, v in usage.items())
        raise HTTPException(
            status_code=409,
            detail=f"No se puede borrar: la usan {detail}. Cámbiales la plataforma antes, o renómbrala.",
        )
    db.delete(platform)
    db.commit()
    return {"message": "Plataforma eliminada"}


# ── Achievements ────────────────────────────────────────────────


@router.get("/achievements")
def list_achievements(db: Session = Depends(get_db)):
    awarded = dict(
        db.query(models.UserAchievement.achievement_id, func.count(models.UserAchievement.id))
        .group_by(models.UserAchievement.achievement_id)
        .all()
    )
    rows = db.query(
        models.Achievement.id,
        models.Achievement.key,
        models.Achievement.title,
        models.Achievement.message,
        (models.Achievement.image.isnot(None)).label("has_image"),
    ).order_by(models.Achievement.id)
    return [
        {
            "id": r.id,
            "key": r.key,
            "title": r.title,
            "message": r.message,
            "has_image": bool(r.has_image),
            "awarded": awarded.get(r.id, 0),
        }
        for r in rows
    ]


class AchievementPatch(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None


@router.patch("/achievements/{achievement_id}")
def patch_achievement(achievement_id: int, body: AchievementPatch, db: Session = Depends(get_db)):
    ach = _get_or_404(db, models.Achievement, achievement_id, "Logro")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ach, k, v)
    db.commit()
    return {"id": ach.id, "key": ach.key, "title": ach.title, "message": ach.message}


# ── Awarded achievements (what each player has unlocked) ────────


def _award_out(ua: models.UserAchievement, username, ach, game_name) -> dict:
    return {
        "id": ua.id,
        "user_id": ua.user_id,
        "user": username,
        "achievement_id": ua.achievement_id,
        "key": ach.key if ach else None,
        "title": ach.title if ach else None,
        "game_id": ua.game_id,
        "game": game_name,
        "date": ua.date,
        "season": ua.season,
    }


@router.get("/user-achievements")
def list_user_achievements(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    achievement_id: Optional[int] = None,
    season: Optional[int] = None,
    sort: str = Query("date", pattern="^(user|achievement|game|date|season)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.UserAchievement, models.User.username, models.Achievement, models.Game.name)
        .outerjoin(models.User, models.User.id == models.UserAchievement.user_id)
        .outerjoin(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
        .outerjoin(models.Game, models.Game.id == models.UserAchievement.game_id)
    )
    if user_id is not None:
        q = q.filter(models.UserAchievement.user_id == user_id)
    if game_id:
        q = q.filter(models.UserAchievement.game_id == game_id)
    if achievement_id is not None:
        q = q.filter(models.UserAchievement.achievement_id == achievement_id)
    if season is not None:
        q = q.filter(models.UserAchievement.season == season)
    total = q.count()
    columns = {
        "user": models.User.username,
        "achievement": models.Achievement.title,
        "game": models.Game.name,
        "date": models.UserAchievement.date,
        "season": models.UserAchievement.season,
    }
    rows = _sorted(q, columns[sort], order, models.UserAchievement.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_award_out(*row) for row in rows]}


class UserAchievementPatch(BaseModel):
    date: datetime.date


@router.patch("/user-achievements/{award_id}")
def patch_user_achievement(award_id: int, body: UserAchievementPatch, db: Session = Depends(get_db)):
    """Change the date an achievement was unlocked (its year decides the season)."""
    ua = _get_or_404(db, models.UserAchievement, award_id, "Logro concedido")
    ua.date = body.date
    _commit(db, "Logro concedido")
    db.refresh(ua)
    return _award_out(ua, None, None, None)


@router.delete("/user-achievements/{award_id}")
def revoke_user_achievement(award_id: int, db: Session = Depends(get_db)):
    """Revoke an unlocked achievement. Nothing is announced. If the player still meets its
    condition, the next achievement check unlocks it again: fix the data behind it first."""
    ua = _get_or_404(db, models.UserAchievement, award_id, "Logro concedido")
    db.delete(ua)
    db.commit()
    return {"message": "Logro revocado"}


# ── Notification settings (Telegram, weekly summary) ────────────


@router.get("/settings")
def get_settings(admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Settings for the admin panel (the Telegram token is never returned, only whether it is set)."""
    jobs = {j.job: {"last_run_at": j.last_run_at, "last_status": j.last_status} for j in db.query(models.JobRun).all()}
    push_devices = {
        "devices": db.query(func.count(models.PushSubscription.id)).scalar(),
        "users": db.query(func.count(func.distinct(models.PushSubscription.user_id))).scalar(),
    }
    # mail comes from the environment, not from app_settings: shown read-only, with where a test goes
    mail_info = {**mail.status(), "test_recipient": admin.email}
    return {
        "values": settings.public_view(db),
        "jobs": jobs,
        "push_devices": push_devices,
        "mail": mail_info,
        "ai_uses": settings.ai_uses(db),
    }


class SettingsBody(BaseModel):
    values: dict


@router.get("/settings/telegram")
def get_telegram_settings(db: Session = Depends(get_db)):
    """Telegram token and chats for the bot process (the token is returned here on purpose).
    `version` changes when any of them does, so the bot knows when to restart."""
    values = settings.get_all(db)
    return {
        "token": values["telegram.token"],
        "group_id": values["telegram.group_id"],
        "admin_chat_id": values["telegram.admin_chat_id"],
        "version": settings.telegram_version(db),
    }


@router.put("/settings")
def put_settings(body: SettingsBody, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Change several settings at once; nothing is stored if one of them is invalid."""
    if any(key.startswith("push.vapid") for key in body.values):
        raise HTTPException(status_code=400, detail="Las claves VAPID se generan con «Generar claves», no se escriben")
    try:
        changed = settings.set_values(db, body.values, user_id=admin.id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"changed": changed, "values": settings.public_view(db)}


@router.post("/settings/push-keys")
def generate_push_keys(replace: bool = False, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Generate the VAPID keys for Web Push. Replacing existing keys invalidates every subscribed device."""
    current = settings.get_all(db)
    if current["push.vapid_private"] and not replace:
        raise HTTPException(status_code=409, detail="Ya hay claves; reemplazarlas obliga a todos a volver a activar los avisos")
    public, private = push.generate_vapid_keys()
    settings.set_values(db, {"push.vapid_public": public, "push.vapid_private": private}, user_id=admin.id)
    if replace:
        db.query(models.PushSubscription).delete()
        db.commit()
    return {"public_key": public}


class AnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=push.TITLE_MAX)
    body: Optional[str] = Field(None, max_length=push.ANNOUNCEMENT_BODY_MAX)
    url: Optional[str] = Field(None, max_length=200)
    image: Optional[str] = Field(None, max_length=500)
    audience: str = Field("me", pattern="^(me|user|group|all)$")
    user_id: Optional[int] = None


@router.get("/push/audience")
def push_audience(db: Session = Depends(get_db)):
    """Who can receive a notice, by channel (for the composer): the devices of the app by audience, and
    whether Telegram has a bot and a group."""
    q = db.query(models.PushSubscription)
    return {
        "ready": push.is_ready(),
        "telegram": {"ready": bool(settings.get("telegram.token")), "group": bool(settings.get("telegram.group_id"))},
        "all": {"devices": q.count(), "users": q.with_entities(func.count(func.distinct(models.PushSubscription.user_id))).scalar()},
        "group": {
            "devices": q.filter(models.PushSubscription.receive_group == True).count(),  # noqa: E712
            "users": q.filter(models.PushSubscription.receive_group == True)  # noqa: E712
            .with_entities(func.count(func.distinct(models.PushSubscription.user_id)))
            .scalar(),
        },
        "users": {
            user_id: devices
            for user_id, devices in q.with_entities(models.PushSubscription.user_id, func.count(models.PushSubscription.id))
            .group_by(models.PushSubscription.user_id)
            .all()
        },
    }


@router.post("/push/announce")
async def send_announcement(
    body: AnnouncementBody,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Send a notice written by an admin to their own devices ("me"), one user's, the group ones or everybody's."""
    if not push.is_ready():
        raise HTTPException(status_code=409, detail="Los avisos push no están listos: revisa que estén activados")
    try:
        payload = push.build_announcement(body.title, body.body, body.url, body.image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user_id = admin.id
    if body.audience == "user":
        if body.user_id is None:
            raise HTTPException(status_code=400, detail="Falta elegir el usuario")
        user_id = _get_or_404(db, models.User, body.user_id, "Usuario").id
    sent, failed = await push.deliver(payload, body.audience, user_id)
    logger.info(f"Announcement by {admin.username} to {body.audience}: {sent} sent, {failed} failed")
    if sent == 0:
        detail = "Ningún dispositivo lo ha aceptado" if failed else "No hay ningún dispositivo suscrito en ese destino"
        raise HTTPException(status_code=404, detail=detail)
    return {"sent": sent, "failed": failed}


class TelegramAnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=push.TITLE_MAX)
    body: Optional[str] = Field(None, max_length=push.ANNOUNCEMENT_BODY_MAX)
    audience: str = Field("me", pattern="^(me|user|group)$")
    user_id: Optional[int] = None


@router.post("/telegram/announce")
async def send_telegram_announcement(
    body: TelegramAnnouncementBody,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Send a notice written by an admin by Telegram only: to their own private chat ("me"), one user's or the
    group's. The app's devices get nothing (see /push/announce for those)."""
    if not settings.get("telegram.token"):
        raise HTTPException(status_code=409, detail="Telegram no está configurado: falta el token del bot")
    if body.audience == "group":
        chat_id, who = settings.get("telegram.group_id"), "el grupo"
        if not chat_id:
            raise HTTPException(status_code=409, detail="Falta el ID del grupo de Telegram")
    else:
        target = admin
        if body.audience == "user":
            if body.user_id is None:
                raise HTTPException(status_code=400, detail="Falta elegir el usuario")
            target = _get_or_404(db, models.User, body.user_id, "Usuario")
        chat_id, who = target.telegram_id, target.username
        if chat_id is None:
            raise HTTPException(status_code=409, detail=f"{target.username} no tiene Telegram ID")
    if not await my_utils.send_announcement_to_chat(chat_id, body.title, body.body):
        raise HTTPException(status_code=502, detail="Telegram no ha aceptado el mensaje")
    logger.info(f"Telegram announcement by {admin.username} to {body.audience}")
    return {"message": f"Enviado a {who}"}


@router.post("/settings/test-message")
async def send_test_message(admin: models.User = Depends(auth.require_admin)):
    """Send a diagnostic message to the configured group."""
    try:
        await my_utils.send_test_message(admin.username)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram no lo ha aceptado: {e}")
    return {"message": "Mensaje enviado"}


@router.post("/settings/test-ai")
def test_ai(admin: models.User = Depends(auth.require_admin)):
    """Ask the AI for one short sentence with the saved provider, key and model (blocking network call:
    a plain def, so it runs in a worker thread). Works with the AI switched off, to try a key before using it."""
    if not settings.get("ai.api_key"):
        raise HTTPException(status_code=409, detail="No hay ninguna clave de IA guardada")
    provider, model = ai.current()
    try:
        reply = ai.complete(
            "Responde solo con una frase corta y divertida sobre videojuegos.", "Saluda al grupo.", force=True
        )
    except ai.AIError as e:
        logger.error(f"AI test by {admin.username} failed: {e}")
        raise HTTPException(status_code=502, detail=f"La IA no ha respondido: {e}")
    return {"message": "La IA ha respondido", "reply": reply, "provider": provider, "model": model}


@router.post("/settings/test-email")
def send_test_email(admin: models.User = Depends(auth.require_admin)):
    """Send a diagnostic email to the email of the admin who asks (blocking SMTP: a plain def, so it
    runs in a worker thread). Tells why when it cannot."""
    missing = mail.missing_settings()
    if missing:
        raise HTTPException(status_code=409, detail="El correo no está configurado: faltan " + ", ".join(missing) + " en el .env")
    if not admin.email:
        raise HTTPException(status_code=400, detail="Tu cuenta no tiene email: añádelo en Usuarios → Editar")
    try:
        mail.send_test_email(admin.email, admin.username)
    except Exception as e:
        logger.error(f"Test email failed: {e}")
        raise HTTPException(status_code=502, detail=f"El servidor de correo no lo ha aceptado: {e}")
    return {"message": f"Correo de prueba enviado a {admin.email}"}

"""Admin panel API: data management for users, games, sessions, library and
achievements. Every route requires an admin (router-level dependency).

Deletes of records that other data hangs from are refused with a 409 that
lists what would be lost, unless `force=true` is passed - the panel shows that
list to the admin and re-sends with force after an explicit confirmation.
"""
import datetime
from typing import Optional

from bcrypt import gensalt, hashpw
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import auth
from ..crud import users as users_crud
from ..database import models
from ..database.database import SessionLocal
from ..utils import actions, my_utils, rawg_sync, seasons, settings
from ..utils.my_utils import normalize_email, validate_email_format, validate_password_requirements, validate_username

router = APIRouter(
    prefix="/manage",
    tags=["Manage"],
    dependencies=[Depends(auth.require_admin)],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


class RecomputeBody(BaseModel):
    user_id: Optional[int] = None
    silent: bool = True


@router.post("/recompute", status_code=202)
def recompute(body: RecomputeBody, background_tasks: BackgroundTasks):
    """Recompute stats/achievements/rankings (all users, or one) in background."""
    background_tasks.add_task(actions.recompute_after_timer_stop, body.user_id, body.silent)
    return {"message": "Recálculo en marcha"}


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


def _checked_email(db: Session, email, *, exclude_user_id=None, required=True):
    """Normalized email that is valid and free (None allowed when not required)."""
    email = normalize_email(email)
    if not email:
        if required:
            raise HTTPException(status_code=400, detail="El email es obligatorio")
        return None
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
    if "email" in data:
        data["email"] = _checked_email(db, data["email"], exclude_user_id=user.id, required=False)
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
    db.query(models.UserStatistics).filter_by(user_id=user_id).delete()
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.Game)
    if search:
        q = q.filter(models.Game.name.like(_like(search)))
    total = q.count()
    games = q.order_by(models.Game.name).limit(limit).offset(offset).all()
    ids = [g.id for g in games]
    sessions = dict(
        db.query(models.GameTimer.game_id, func.count(models.GameTimer.id))
        .filter(models.GameTimer.game_id.in_(ids))
        .group_by(models.GameTimer.game_id)
        .all()
    )
    players = dict(
        db.query(models.UserGame.game_id, func.count(func.distinct(models.UserGame.user_id)))
        .filter(models.UserGame.game_id.in_(ids))
        .group_by(models.UserGame.game_id)
        .all()
    )
    return {"total": total, "items": [_game_out(g, sessions.get(g.id, 0), players.get(g.id, 0)) for g in games]}


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
    db.query(models.GameStatistics).filter_by(game_id=game_id).delete()
    db.delete(game)
    db.commit()
    return {"message": "Juego eliminado"}


class MergeBody(BaseModel):
    target_id: str


@router.post("/games/{game_id}/merge")
def merge_game(game_id: str, body: MergeBody, db: Session = Depends(get_db)):
    """Move everything from `game_id` (duplicate) into `target_id`, then delete it.

    Rows that would collide with an existing one on the target (same session
    start, or same user+platform+season in the library) are dropped from the
    duplicate instead of moved.
    """
    if game_id == body.target_id:
        raise HTTPException(status_code=400, detail="El origen y el destino son el mismo juego")
    source = _get_or_404(db, models.Game, game_id, "Juego origen")
    target = _get_or_404(db, models.Game, body.target_id, "Juego destino")

    moved = {"sesiones": 0, "biblioteca": 0, "logros": 0}
    dropped = {"sesiones": 0, "biblioteca": 0, "logros": 0}

    taken_starts = {
        (t.user_id, t.start_time) for t in db.query(models.GameTimer).filter_by(game_id=target.id)
    }
    for t in db.query(models.GameTimer).filter_by(game_id=source.id).all():
        if (t.user_id, t.start_time) in taken_starts:
            db.delete(t)
            dropped["sesiones"] += 1
        else:
            t.game_id = target.id
            moved["sesiones"] += 1

    taken_lib = {
        (u.user_id, u.platform, u.season) for u in db.query(models.UserGame).filter_by(game_id=target.id)
    }
    for u in db.query(models.UserGame).filter_by(game_id=source.id).all():
        if (u.user_id, u.platform, u.season) in taken_lib:
            db.delete(u)
            dropped["biblioteca"] += 1
        else:
            u.game_id = target.id
            moved["biblioteca"] += 1

    # users_achievements.game_id is informational; repoint it (no game-based uniqueness).
    n = db.query(models.UserAchievement).filter_by(game_id=source.id).update({"game_id": target.id})
    moved["logros"] = n

    db.query(models.GameStatistics).filter_by(game_id=source.id).delete()
    db.delete(source)
    _commit(db, "Fusión")
    return {"message": "Juegos fusionados", "moved": moved, "dropped": dropped}


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
    total = q.count()
    rows = q.order_by(models.GameTimer.start_time.desc()).limit(limit).offset(offset).all()
    return {"total": total, "items": [_timer_out(t, u, g) for t, u, g in rows]}


def _ensure_library(db: Session, user_id: int, game_id: str, platform, when: datetime.datetime):
    """Same guarantee create_timer gives: a users_games row per (game, platform, season of `when`)."""
    exists = (
        db.query(models.UserGame)
        .filter_by(user_id=user_id, game_id=game_id, platform=platform, season=seasons.of(when))
        .first()
    )
    if exists is None:
        db.add(
            models.UserGame(
                user_id=user_id,
                game_id=game_id,
                platform=platform,
                completed=0,
                started_date=when.date(),
            )
        )


class TimerCreate(BaseModel):
    user_id: int
    game_id: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    platform: Optional[str] = None
    notes: Optional[str] = None


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
    _ensure_library(db, body.user_id, body.game_id, body.platform, body.start_time)
    _commit(db, "Sesión")
    return _timer_out(timer, None, None)


class TimerPatch(BaseModel):
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    platform: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/timers/{timer_id}")
def patch_timer(timer_id: int, body: TimerPatch, db: Session = Depends(get_db)):
    """Edit a session. Setting an end time finishes an active one (stuck timer)."""
    timer = _get_or_404(db, models.GameTimer, timer_id, "Sesión")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(timer, k, v)
    _check_range(timer.start_time, timer.end_time)
    if timer.end_time is not None:
        timer.duration_seconds = int((timer.end_time - timer.start_time).total_seconds())
        timer.is_active = False
    _commit(db, "Sesión")
    return _timer_out(timer, None, None)


@router.delete("/timers/{timer_id}")
def delete_timer(timer_id: int, db: Session = Depends(get_db)):
    timer = _get_or_404(db, models.GameTimer, timer_id, "Sesión")
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
    total = q.count()
    rows = q.order_by(models.UserGame.season.desc(), models.UserGame.id.desc()).limit(limit).offset(offset).all()
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


# ── Notification settings (Telegram, weekly summary) ────────────


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """Settings for the admin panel (the Telegram token is never returned, only whether it is set)."""
    jobs = {j.job: {"last_run_at": j.last_run_at, "last_status": j.last_status} for j in db.query(models.JobRun).all()}
    return {"values": settings.public_view(db), "jobs": jobs}


class SettingsBody(BaseModel):
    values: dict


@router.put("/settings")
def put_settings(body: SettingsBody, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Change several settings at once; nothing is stored if one of them is invalid."""
    try:
        changed = settings.set_values(db, body.values, user_id=admin.id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"changed": changed, "values": settings.public_view(db)}


@router.post("/settings/test-message")
async def send_test_message(admin: models.User = Depends(auth.require_admin)):
    """Send a diagnostic message to the configured group."""
    try:
        await my_utils.send_test_message(admin.username)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram no lo ha aceptado: {e}")
    return {"message": "Mensaje enviado"}

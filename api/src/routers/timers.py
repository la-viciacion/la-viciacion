import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import auth
from ..crud import users as users_crud
from ..database.database import SessionLocal
from ..database.models import Game, GameTimer, PlatformTag, User, UserGame
from ..database.schemas import (
    ActiveTimerResponse,
    GameTimerCreate,
    GameTimerGroup,
    GameTimerGroupPage,
    GameTimerResponse,
    GamePlatformsResponse,
    GameTimerUpdate,
    ManualSessionCreate,
    NewGameUser,
    SessionUpdate,
    TimerStats,
)
from ..utils import actions
from ..utils import seasons


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Timer CRUD operations
def check_new_timer(db: Session, timer: GameTimerCreate) -> None:
    """The game (and the platform, when given) of a new timer must exist: nothing in the
    schema enforces it and a timer of an unknown game breaks every page that lists it."""
    if db.query(User.id).filter(User.id == timer.user_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if db.query(Game.id).filter(Game.id == timer.game_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Juego no encontrado")
    if timer.platform is not None:
        _valid_platform(db, timer.platform)


async def create_timer(db: Session, timer: GameTimerCreate) -> tuple[GameTimer, bool]:
    """Start the timer. Returns it and whether the group must be told about a new game
    (the announcement is slow, so the caller sends it in the background)."""
    check_new_timer(db, timer)
    # Check if user already has an active timer
    active_timer = db.query(GameTimer).filter(
        GameTimer.user_id == timer.user_id,
        GameTimer.is_active == True
    ).first()

    if active_timer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has an active timer. Stop it first."
        )

    # A timer never starts before the user's last finished session ended (manual
    # entries may end a minute "ahead" of the server clock): one game at a time.
    last_end = (
        db.query(func.max(GameTimer.end_time))
        .filter(GameTimer.user_id == timer.user_id)
        .scalar()
    )
    started = datetime.datetime.now()
    if last_end is not None and last_end > started:
        started = last_end

    db_timer = GameTimer(
        user_id=timer.user_id,
        game_id=timer.game_id,
        start_time=started,
        platform=timer.platform,
        notes=timer.notes,
        is_active=True
    )
    db.add(db_timer)
    db.commit()
    db.refresh(db_timer)

    # Make sure the user has a UserGame entry for this game/season.
    season = seasons.current()
    user = users_crud.get_user_by_id(db, timer.user_id)
    # One UserGame per (game, platform, season): the same game on another
    # platform, or in a later year, is a new entry.
    already_playing = (
        db.query(UserGame)
        .filter_by(
            user_id=timer.user_id,
            game_id=timer.game_id,
            platform=timer.platform,
            season=season,
        )
        .first()
    )
    announce = False
    if already_playing is None and user is not None:
        # "new game" is announced the first time the user plays a game in a season,
        # whatever the platform: the same game on another platform is only a new entry
        announce = (
            db.query(UserGame.id)
            .filter_by(user_id=timer.user_id, game_id=timer.game_id, season=season)
            .first()
            is None
        )
        await users_crud.add_new_game(
            db,
            game=NewGameUser(game_id=timer.game_id, platform=timer.platform),
            user=user,
            announce=False,
        )

    return db_timer, announce


def get_active_timer(db: Session, user_id: int) -> Optional[GameTimer]:
    return db.query(GameTimer).filter(
        GameTimer.user_id == user_id,
        GameTimer.is_active == True
    ).first()


def stop_timer(db: Session, timer_id: int, user_id: int) -> GameTimer:
    timer = db.query(GameTimer).filter(
        GameTimer.id == timer_id,
        GameTimer.user_id == user_id,
        GameTimer.is_active == True
    ).first()
    
    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active timer not found"
        )
    
    timer.end_time = datetime.datetime.now()
    timer.duration_seconds = int((timer.end_time - timer.start_time).total_seconds())
    timer.is_active = False

    db.commit()
    db.refresh(timer)
    return timer


def get_timer_history(db: Session, user_id: int, game_id: Optional[str] = None, limit: int = 100) -> List[GameTimer]:
    query = db.query(GameTimer).filter(GameTimer.user_id == user_id)
    
    if game_id:
        query = query.filter(GameTimer.game_id == game_id)
    
    return query.order_by(GameTimer.start_time.desc()).limit(limit).all()


def get_grouped_timer_history(
    db: Session, user_id: int, limit: int, offset: int, sessions_per_game: int
) -> GameTimerGroupPage:
    """Finished sessions collapsed per game, most recently played game first."""
    finished = (GameTimer.user_id == user_id, GameTimer.is_active == False)

    total_games = (
        db.query(func.count(func.distinct(GameTimer.game_id))).filter(*finished).scalar() or 0
    )

    page = (
        db.query(
            GameTimer.game_id,
            func.max(GameTimer.start_time).label("last_played"),
            func.coalesce(func.sum(GameTimer.duration_seconds), 0).label("total_seconds"),
            func.count(GameTimer.id).label("session_count"),
        )
        .filter(*finished)
        .group_by(GameTimer.game_id)
        .order_by(func.max(GameTimer.start_time).desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    groups: List[GameTimerGroup] = []
    for row in page:
        game = db.query(Game).filter(Game.id == row.game_id).first()
        sessions = (
            db.query(GameTimer)
            .filter(*finished, GameTimer.game_id == row.game_id)
            .order_by(GameTimer.start_time.desc())
            .limit(sessions_per_game)
            .all()
        )
        platforms = [
            r.platform
            for r in db.query(GameTimer.platform)
            .filter(*finished, GameTimer.game_id == row.game_id, GameTimer.platform.isnot(None))
            .group_by(GameTimer.platform)
            .order_by(func.max(GameTimer.start_time).desc())
            .all()
        ]
        groups.append(
            GameTimerGroup(
                game_id=row.game_id,
                game_name=game.name if game else None,
                image_url=game.image_url if game else None,
                platform=sessions[0].platform if sessions else None,
                platforms=platforms,
                last_played=row.last_played,
                total_seconds=int(row.total_seconds),
                session_count=row.session_count,
                sessions=sessions,
            )
        )

    return GameTimerGroupPage(groups=groups, total_games=total_games)


def get_timer_stats(db: Session, user_id: int, game_id: Optional[str] = None) -> TimerStats:
    query = db.query(GameTimer).filter(
        GameTimer.user_id == user_id,
        GameTimer.is_active == False
    )
    
    if game_id:
        query = query.filter(GameTimer.game_id == game_id)
    
    timers = query.all()
    
    if not timers:
        return TimerStats(
            user_id=user_id,
            game_id=game_id,
            total_time_seconds=0,
            total_sessions=0,
            average_session_duration=0.0,
            longest_session_seconds=0,
            shortest_session_seconds=0
        )
    
    total_time = sum(t.duration_seconds or 0 for t in timers)
    total_sessions = len(timers)
    avg_duration = total_time / total_sessions if total_sessions > 0 else 0
    longest = max(t.duration_seconds or 0 for t in timers)
    shortest = min(t.duration_seconds or 0 for t in timers)
    
    return TimerStats(
        user_id=user_id,
        game_id=game_id,
        total_time_seconds=total_time,
        total_sessions=total_sessions,
        average_session_duration=avg_duration,
        longest_session_seconds=longest,
        shortest_session_seconds=shortest
    )


# ── Manual sessions: enter, correct or remove a finished session ──────────

MAX_SESSION = datetime.timedelta(hours=24)
FUTURE_SLACK = datetime.timedelta(minutes=1)


def _reject(code: int, message: str):
    raise HTTPException(status_code=code, detail=message)


def _check_season(current_user: User, *days: datetime.date | datetime.datetime):
    """Only the running season can be edited by its owner (closed seasons are frozen; admins may)."""
    current = seasons.current()
    if not current_user.is_admin and any(seasons.of(d) != current for d in days):
        _reject(400, f"Solo se pueden registrar, editar o borrar sesiones de la temporada actual ({current})")


def validate_session(
    db: Session,
    current_user: User,
    user_id: int,
    start: datetime.datetime,
    end: datetime.datetime,
    exclude_id: int | None = None,
) -> None:
    """Rules for a finished session (create and edit): sensible times, current season,
    and no overlap with anything else the same user played (or is playing)."""
    if end <= start:
        _reject(400, "El fin debe ser posterior al inicio")
    if end > datetime.datetime.now() + FUTURE_SLACK:
        _reject(400, "La sesión no puede terminar en el futuro")
    if end - start > MAX_SESSION:
        _reject(400, "Una sesión no puede durar más de 24 horas")
    _check_season(current_user, start, end)

    overlapping = (
        db.query(GameTimer)
        .filter(
            GameTimer.user_id == user_id,
            GameTimer.start_time < end,
            or_(GameTimer.end_time.is_(None), GameTimer.end_time > start),
        )
    )
    if exclude_id is not None:
        overlapping = overlapping.filter(GameTimer.id != exclude_id)
    other = overlapping.first()
    if other is not None:
        game = db.query(Game).filter(Game.id == other.game_id).first()
        when = other.start_time.strftime("%d/%m %H:%M") + (
            "" if other.end_time is None else " a " + other.end_time.strftime("%H:%M")
        )
        _reject(409, f"Se solapa con otra sesión ({game.name if game else other.game_id}, {when})")


def _valid_platform(db: Session, platform: str | None) -> str:
    if not platform or db.query(PlatformTag.id).filter(PlatformTag.id == platform).first() is None:
        _reject(400, "Plataforma no válida")
    return platform


def _commit_session(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _reject(409, "Ya tienes una sesión de ese juego que empieza a esa hora")


def create_manual_session(db: Session, current_user: User, body: ManualSessionCreate) -> GameTimer:
    user_id = body.user_id if body.user_id is not None else current_user.id
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    if db.query(Game.id).filter(Game.id == body.game_id).first() is None:
        _reject(404, "Juego no encontrado")
    platform = _valid_platform(db, body.platform)
    validate_session(db, current_user, user_id, body.start_time, body.end_time)

    timer = GameTimer(
        user_id=user_id,
        game_id=body.game_id,
        start_time=body.start_time,
        end_time=body.end_time,
        duration_seconds=int((body.end_time - body.start_time).total_seconds()),
        platform=platform,
        notes=body.notes,
        is_active=False,
    )
    db.add(timer)
    # the library entry of that game/platform/season, without announcing "new game"
    users_crud.ensure_library_entry(db, user_id, body.game_id, platform, body.start_time)
    _commit_session(db)
    db.refresh(timer)
    return timer


def _own_finished_session(db: Session, current_user: User, timer_id: int) -> GameTimer:
    timer = db.query(GameTimer).filter(GameTimer.id == timer_id).first()
    if timer is None:
        _reject(404, "Sesión no encontrada")
    auth.ensure_self_or_admin(current_user, user_id=timer.user_id)
    if timer.is_active:
        _reject(409, "Es un timer en curso: páralo antes de editarlo")
    return timer


def update_session(db: Session, current_user: User, timer_id: int, body: SessionUpdate) -> GameTimer:
    timer = _own_finished_session(db, current_user, timer_id)
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_time") or timer.start_time
    end = data.get("end_time") or timer.end_time
    # a session of a closed season cannot be edited by its owner, nor moved out of the current one
    _check_season(current_user, timer.start_time)
    validate_session(db, current_user, timer.user_id, start, end, exclude_id=timer.id)
    if "platform" in data:
        timer.platform = _valid_platform(db, data["platform"])
    if "notes" in data:
        timer.notes = data["notes"]
    timer.start_time, timer.end_time = start, end
    timer.duration_seconds = int((end - start).total_seconds())
    users_crud.ensure_library_entry(db, timer.user_id, timer.game_id, timer.platform, start)
    _commit_session(db)
    db.refresh(timer)
    return timer


def delete_session(db: Session, current_user: User, timer_id: int) -> None:
    timer = _own_finished_session(db, current_user, timer_id)
    _check_season(current_user, timer.start_time)
    db.delete(timer)
    db.commit()


# FastAPI Router
router = APIRouter(
    prefix="/timers",
    tags=["timers"],
    # Every route needs a logged-in user; each one also checks the data
    # belongs to them (or that they are an admin).
)


@router.post("/start", response_model=GameTimerResponse)
async def start_timer(
    timer: GameTimerCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Start a new game timer for a user"""
    auth.ensure_self_or_admin(current_user, user_id=timer.user_id)
    started, new_game = await create_timer(db, timer)
    background_tasks.add_task(
        actions.after_timer_start,
        started.user_id,
        started.start_time,
        started.game_id if new_game else None,
    )
    return started


@router.post("/manual", response_model=GameTimerResponse, status_code=status.HTTP_201_CREATED)
def create_manual_session_endpoint(
    body: ManualSessionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a finished session by hand: game, platform, start and end."""
    timer = create_manual_session(db, current_user, body)
    # silent: retroactive entries do not announce rankings/achievements to the group
    background_tasks.add_task(actions.after_session_change, timer.user_id, True)
    return timer


@router.patch("/{timer_id}", response_model=GameTimerResponse)
def update_session_endpoint(
    timer_id: int,
    body: SessionUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Correct a finished session (platform, start, end)."""
    timer = update_session(db, current_user, timer_id, body)
    background_tasks.add_task(actions.after_session_change, timer.user_id, True)
    return timer


@router.delete("/{timer_id}")
def delete_session_endpoint(
    timer_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove a finished session (entered by mistake)."""
    owner = db.query(GameTimer.user_id).filter(GameTimer.id == timer_id).scalar()
    delete_session(db, current_user, timer_id)
    background_tasks.add_task(actions.after_session_change, owner, True)
    return {"message": "Sesión eliminada"}


@router.get("/active/{user_id}", response_model=ActiveTimerResponse)
def get_active_timer_endpoint(
    user_id: int,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get the currently active timer for a user"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    active_timer = get_active_timer(db, user_id)
    
    if active_timer:
        return ActiveTimerResponse(
            is_active=True,
            timer=active_timer
        )
    else:
        return ActiveTimerResponse(
            is_active=False,
            timer=None
        )


@router.post("/stop/{timer_id}", response_model=GameTimerResponse)
def stop_timer_endpoint(
    timer_id: int,
    user_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Stop an active timer"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    ranking_before = actions.ranking_snapshot(db)
    timer = stop_timer(db, timer_id, user_id)
    background_tasks.add_task(actions.after_session_change, user_id, False, ranking_before)
    return timer


@router.get("/history/{user_id}", response_model=List[GameTimerResponse])
def get_timer_history_endpoint(
    user_id: int, 
    game_id: Optional[str] = None, 
    limit: int = 100,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get timer history for a user, optionally filtered by game"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    return get_timer_history(db, user_id, game_id, limit)


@router.get("/history/{user_id}/grouped", response_model=GameTimerGroupPage)
def get_grouped_timer_history_endpoint(
    user_id: int,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    sessions_per_game: int = Query(10, ge=1, le=50),
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Timer history grouped by game (one row per game), newest game first"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    return get_grouped_timer_history(db, user_id, limit, offset, sessions_per_game)


@router.get("/history/{user_id}/platforms/{game_id}", response_model=GamePlatformsResponse)
def get_game_platforms_endpoint(
    user_id: int,
    game_id: str,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """What the user has already played of a game: whether there is any history
    and which platforms were used (most recent first)."""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    rows = (
        db.query(GameTimer.platform)
        .filter(
            GameTimer.user_id == user_id,
            GameTimer.game_id == game_id,
            GameTimer.platform.isnot(None),
        )
        .group_by(GameTimer.platform)
        .order_by(func.max(GameTimer.start_time).desc())
        .all()
    )
    platforms = [r.platform for r in rows]
    # Platforms registered on the user's library entry also count (sessions
    # without a platform, or a game added without any timer yet).
    library = (
        db.query(UserGame.platform)
        .filter(
            UserGame.user_id == user_id,
            UserGame.game_id == game_id,
            UserGame.platform.isnot(None),
        )
        .order_by(UserGame.season.desc())
        .all()
    )
    for r in library:
        if r.platform not in platforms:
            platforms.append(r.platform)

    has_history = bool(platforms) or (
        db.query(GameTimer.id)
        .filter(GameTimer.user_id == user_id, GameTimer.game_id == game_id)
        .first()
        is not None
    )
    return GamePlatformsResponse(has_history=has_history, platforms=platforms)


@router.get("/stats/{user_id}", response_model=TimerStats)
def get_timer_stats_endpoint(
    user_id: int, 
    game_id: Optional[str] = None,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get timer statistics for a user, optionally filtered by game"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    return get_timer_stats(db, user_id, game_id)

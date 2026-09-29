import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..crud import users as users_crud
from ..database.database import SessionLocal
from ..database.models import Game, GameTimer, UserGame
from ..database.schemas import (
    ActiveTimerResponse,
    GameTimerCreate,
    GameTimerGroup,
    GameTimerGroupPage,
    GameTimerResponse,
    GamePlatformsResponse,
    GameTimerUpdate,
    NewGameUser,
    TimerStats,
)
from ..utils import actions


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close


# Timer CRUD operations
async def create_timer(db: Session, timer: GameTimerCreate) -> GameTimer:
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

    db_timer = GameTimer(
        user_id=timer.user_id,
        game_id=timer.game_id,
        start_time=datetime.datetime.now(),
        platform=timer.platform,
        season=timer.season,
        notes=timer.notes,
        is_active=True
    )
    db.add(db_timer)
    db.commit()
    db.refresh(db_timer)

    # Make sure the user has a UserGame entry for this game/season, same as
    # the Clockify sync used to create implicitly when a time entry came in.
    season = timer.season or datetime.datetime.now().year
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
    if already_playing is None and user is not None:
        await users_crud.add_new_game(
            db,
            game=NewGameUser(game_id=timer.game_id, platform=timer.platform),
            user=user,
            season=season,
            silent=False,
        )

    return db_timer


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


# FastAPI Router
router = APIRouter(prefix="/timers", tags=["timers"])


@router.post("/start", response_model=GameTimerResponse)
async def start_timer(timer: GameTimerCreate, db: Session = Depends(get_db)):
    """Start a new game timer for a user"""
    return await create_timer(db, timer)


@router.get("/active/{user_id}", response_model=ActiveTimerResponse)
def get_active_timer_endpoint(user_id: int, db: Session = Depends(get_db)):
    """Get the currently active timer for a user"""
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
    db: Session = Depends(get_db),
):
    """Stop an active timer"""
    timer = stop_timer(db, timer_id, user_id)
    background_tasks.add_task(actions.recompute_after_timer_stop, user_id)
    return timer


@router.get("/history/{user_id}", response_model=List[GameTimerResponse])
def get_timer_history_endpoint(
    user_id: int, 
    game_id: Optional[str] = None, 
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get timer history for a user, optionally filtered by game"""
    return get_timer_history(db, user_id, game_id, limit)


@router.get("/history/{user_id}/grouped", response_model=GameTimerGroupPage)
def get_grouped_timer_history_endpoint(
    user_id: int,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    sessions_per_game: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Timer history grouped by game (one row per game), newest game first"""
    return get_grouped_timer_history(db, user_id, limit, offset, sessions_per_game)


@router.get("/history/{user_id}/platforms/{game_id}", response_model=GamePlatformsResponse)
def get_game_platforms_endpoint(user_id: int, game_id: str, db: Session = Depends(get_db)):
    """What the user has already played of a game: whether there is any history
    and which platforms were used (most recent first)."""
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
    db: Session = Depends(get_db)
):
    """Get timer statistics for a user, optionally filtered by game"""
    return get_timer_stats(db, user_id, game_id)

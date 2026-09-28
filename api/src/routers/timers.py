import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..crud import users as users_crud
from ..database.database import SessionLocal
from ..database.models import GameTimer
from ..database.schemas import (
    ActiveTimerResponse,
    GameTimerCreate,
    GameTimerResponse,
    GameTimerUpdate,
    NewGameUser,
    TimerStats,
)
from ..utils import actions
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()


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
    already_playing = users_crud.get_game_by_id(db, timer.user_id, timer.game_id, season)
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


async def recompute_after_timer_stop():
    """Recompute stats/rankings/achievements after a native timer session closes.

    Runs as a background task with its own DB session (the request-scoped
    session is already closed by the time this executes). While the Clockify
    sync still runs in parallel, this reuses actions.sync_data as-is; once the
    Clockify cutover happens this will point at its Clockify-free replacement.
    """
    db = SessionLocal()
    try:
        await actions.sync_data(db, silent=True)
    except Exception as e:
        logger.error("Error recomputing stats after timer stop: " + str(e))
    finally:
        db.close()


def get_timer_history(db: Session, user_id: int, game_id: Optional[str] = None, limit: int = 100) -> List[GameTimer]:
    query = db.query(GameTimer).filter(GameTimer.user_id == user_id)
    
    if game_id:
        query = query.filter(GameTimer.game_id == game_id)
    
    return query.order_by(GameTimer.start_time.desc()).limit(limit).all()


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
    background_tasks.add_task(recompute_after_timer_stop)
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


@router.get("/stats/{user_id}", response_model=TimerStats)
def get_timer_stats_endpoint(
    user_id: int, 
    game_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get timer statistics for a user, optionally filtered by game"""
    return get_timer_stats(db, user_id, game_id)

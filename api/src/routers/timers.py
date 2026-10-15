from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import scores as scores_crud
from ..crud import time_entries, timers
from ..database.models import User
from ..database.schemas import (
    ActiveTimerResponse,
    GameTimerCreate,
    GameTimerGroupPage,
    GameTimerResponse,
    GamePlatformsResponse,
    ManualSessionCreate,
    SessionUpdate,
)
from ..utils import actions
from ..utils import seasons
from ..utils.refusal import RefusedRoute


def _by_admin(current_user: User, user_id: int) -> bool:
    """True when an admin changes somebody else's sessions: their changes check the player silently."""
    return current_user.id != user_id


router = APIRouter(
    prefix="/timers",
    tags=["timers"],
    route_class=RefusedRoute,
    # Every route needs a logged-in user; each one also checks the data
    # belongs to them (or that they are an admin). The rules themselves are in crud/timers.py.
)


@router.post("/start", response_model=GameTimerResponse)
def start_timer(
    timer: GameTimerCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Start a new game timer for a user"""
    auth.ensure_self_or_admin(current_user, user_id=timer.user_id)
    started, new_game = timers.create_timer(db, timer)
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
    user_id = body.user_id if body.user_id is not None else current_user.id
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    timer = timers.create_manual_session(db, current_user, user_id, body)
    # what it earns is announced and what it cannot hold is revoked; the rankings are not (it is a retroactive entry)
    background_tasks.add_task(
        actions.after_session_change, timer.user_id, _by_admin(current_user, timer.user_id),
        recalculate=[seasons.of(timer.start_time)], since=timer.start_time.date(),
    )
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
    timer = timers.get_session(db, timer_id)
    auth.ensure_self_or_admin(current_user, user_id=timer.user_id)
    old_start = timer.start_time
    timer = timers.update_session(db, current_user, timer, body)
    # the achievements of the seasons it was in and is in now are worked out again: it may no longer earn what it did
    changed = sorted({seasons.of(old_start), seasons.of(timer.start_time)})
    background_tasks.add_task(
        actions.after_session_change, timer.user_id, _by_admin(current_user, timer.user_id),
        recalculate=changed, since=min(old_start, timer.start_time).date(),
    )
    return timer


@router.delete("/{timer_id}")
def delete_session_endpoint(
    timer_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove a finished session (entered by mistake)."""
    timer = timers.get_session(db, timer_id)
    auth.ensure_self_or_admin(current_user, user_id=timer.user_id)
    owner, start = timer.user_id, timer.start_time
    timers.delete_session(db, current_user, timer)
    background_tasks.add_task(
        actions.after_session_change, owner, _by_admin(current_user, owner), recalculate=[seasons.of(start)], since=start.date()
    )
    return {"message": "Sesión eliminada"}


@router.get("/now-playing")
def now_playing(
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Who is playing right now (visible to every logged-in player; each one can hide themselves)"""
    return time_entries.get_now_playing(db, current_user.id)


@router.get("/active/{user_id}", response_model=ActiveTimerResponse)
def get_active_timer_endpoint(
    user_id: int,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The user's running timer, with the game's name and their rating of it"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    active_timer = timers.get_active_timer(db, user_id)
    if active_timer is None:
        return ActiveTimerResponse(is_active=False, timer=None)
    return ActiveTimerResponse(
        is_active=True,
        timer=active_timer,
        game_name=timers.game_name(db, active_timer.game_id),
        score=scores_crud.user_scores(db, user_id).get(active_timer.game_id),
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
    timer = timers.stop_timer(db, timer_id, user_id)
    background_tasks.add_task(
        actions.after_session_change, user_id, False, ranking_before,
        stopped=(timer.game_id, timer.start_time, timer.duration_seconds),
    )
    background_tasks.add_task(actions.after_timer_stop, user_id, timer.game_id, timer.duration_seconds)
    return timer


@router.delete("/cancel/{timer_id}")
def cancel_timer_endpoint(
    timer_id: int,
    user_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cancel an active timer: it is deleted, not recorded"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    timer = timers.cancel_timer(db, timer_id, user_id)
    background_tasks.add_task(actions.after_timer_stop, user_id, timer.game_id, None)
    return {"message": "Timer cancelado"}


@router.get("/history/{user_id}", response_model=list[GameTimerResponse])
def get_timer_history_endpoint(
    user_id: int,
    game_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get timer history for a user, optionally filtered by game"""
    auth.ensure_self_or_admin(current_user, user_id=user_id)
    return timers.get_timer_history(db, user_id, game_id, limit)


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
    return timers.get_grouped_timer_history(db, user_id, limit, offset, sessions_per_game)


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
    has_history, platforms = timers.game_platforms(db, user_id, game_id)
    return GamePlatformsResponse(has_history=has_history, platforms=platforms)

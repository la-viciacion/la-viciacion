"""A player's data: sessions (game_timers), library (users_games) and ratings (game_scores)."""
import datetime
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...auth import get_db
from ...crud import users as users_crud
from ...database import models
from ...utils import actions, seasons
from ...database.schemas import NOTES_MAX
from .common import commit, get_or_404, ordered, router


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
    rows = ordered(q, columns[sort], order, models.GameTimer.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_timer_out(t, u, g) for t, u, g in rows]}


class TimerCreate(BaseModel):
    user_id: int
    game_id: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    platform: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_MAX)


def _recheck_achievements(background_tasks: BackgroundTasks, user_id: int, season_list: list[int]) -> None:
    """Whatever an admin changes in the sessions or the library of a player can earn them an achievement or
    take one away: their achievements of those seasons are worked out again, silently (nothing is announced)."""
    background_tasks.add_task(actions.after_session_change, user_id, True, recalculate=season_list)


def _check_range(start: datetime.datetime, end: Optional[datetime.datetime]):
    if end is not None and end <= start:
        raise HTTPException(status_code=400, detail="El fin debe ser posterior al inicio")


@router.post("/timers", status_code=201)
def create_timer(body: TimerCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Create a finished session by hand (e.g. a forgotten timer)."""
    get_or_404(db, models.User, body.user_id, "Usuario")
    get_or_404(db, models.Game, body.game_id, "Juego")
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
    commit(db, "Sesión")
    _recheck_achievements(background_tasks, body.user_id, [seasons.of(body.start_time)])
    return _timer_out(timer, None, None)


class TimerPatch(BaseModel):
    game_id: Optional[str] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    platform: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_MAX)


def _follow_library(db: Session, timer: models.GameTimer, old_entry: tuple) -> None:
    """A session that changed game, platform or season takes its library entry along: the new one is
    created if missing and the old one goes when nothing is left in it (a completed one is kept)."""
    new_entry = (timer.game_id, timer.platform, seasons.of(timer.start_time))
    if new_entry == old_entry:
        return
    users_crud.ensure_library_entry(db, timer.user_id, timer.game_id, timer.platform, timer.start_time)
    db.flush()
    users_crud.drop_empty_entry(db, timer.user_id, *old_entry)


@router.patch("/timers/{timer_id}")
def patch_timer(timer_id: int, body: TimerPatch, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Edit a session. Setting an end time finishes an active one (stuck timer). Changing the game (a
    session logged on the wrong one) is for admins only: the owner deletes and re-adds."""
    timer = get_or_404(db, models.GameTimer, timer_id, "Sesión")
    was_running = bool(timer.is_active)
    data = body.model_dump(exclude_unset=True)
    if data.get("game_id") is None:
        data.pop("game_id", None)
    else:
        get_or_404(db, models.Game, data["game_id"], "Juego")
    old_entry = (timer.game_id, timer.platform, seasons.of(timer.start_time))
    for k, v in data.items():
        setattr(timer, k, v)
    _check_range(timer.start_time, timer.end_time)
    if timer.end_time is not None:
        timer.duration_seconds = int((timer.end_time - timer.start_time).total_seconds())
        timer.is_active = False
    _follow_library(db, timer, old_entry)
    commit(db, "Sesión")
    if was_running and not timer.is_active:
        # a stuck timer was finished by hand: its pinned notification has to go
        background_tasks.add_task(actions.after_timer_stop, timer.user_id, timer.game_id, timer.duration_seconds)
    _recheck_achievements(background_tasks, timer.user_id, sorted({old_entry[2], seasons.of(timer.start_time)}))
    return _timer_out(timer, None, None)


@router.delete("/timers/{timer_id}")
def delete_timer(timer_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    timer = get_or_404(db, models.GameTimer, timer_id, "Sesión")
    if timer.is_active:
        background_tasks.add_task(actions.after_timer_stop, timer.user_id, timer.game_id, None)
    user_id, season = timer.user_id, seasons.of(timer.start_time)
    db.delete(timer)
    db.commit()
    _recheck_achievements(background_tasks, user_id, [season])
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
        "abandoned_at": u.abandoned_at,
    }


@router.get("/library")
def list_library(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    season: Optional[int] = None,
    platform: Optional[str] = None,
    completed: Optional[str] = Query(None, pattern="^(yes|no)$"),
    sort: str = Query("season", pattern="^(user|game|platform|season|started|completed)$"),
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
    }
    rows = ordered(q, columns[sort], order, models.UserGame.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_library_out(u, un, gn) for u, un, gn in rows]}


class LibraryCreate(BaseModel):
    user_id: int
    game_id: str
    platform: Optional[str] = None
    started_date: Optional[datetime.date] = None  # its year is the entry's season (default: today)


@router.post("/library", status_code=201)
def create_library(body: LibraryCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    get_or_404(db, models.User, body.user_id, "Usuario")
    get_or_404(db, models.Game, body.game_id, "Juego")
    row = models.UserGame(
        user_id=body.user_id,
        game_id=body.game_id,
        platform=body.platform,
        completed=0,
        started_date=body.started_date or datetime.date.today(),
    )
    db.add(row)
    commit(db, "Biblioteca")
    _recheck_achievements(background_tasks, body.user_id, [seasons.of(row.started_date)])
    return _library_out(row, None, None)


class LibraryPatch(BaseModel):
    platform: Optional[str] = None
    started_date: Optional[datetime.date] = None
    completed: Optional[bool] = None
    completed_date: Optional[datetime.date] = None
    abandoned_at: Optional[datetime.datetime] = None


@router.patch("/library/{row_id}")
def patch_library(row_id: int, body: LibraryPatch, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    row = get_or_404(db, models.UserGame, row_id, "Entrada de biblioteca")
    data = body.model_dump(exclude_unset=True)
    if "completed" in data and data["completed"] is not None:
        data["completed"] = int(data["completed"])
    season_before = seasons.of(row.started_date)
    for k, v in data.items():
        setattr(row, k, v)
    commit(db, "Biblioteca")
    _recheck_achievements(background_tasks, row.user_id, sorted({season_before, seasons.of(row.started_date)}))
    return _library_out(row, None, None)


@router.delete("/library/{row_id}")
def delete_library(row_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    row = get_or_404(db, models.UserGame, row_id, "Entrada de biblioteca")
    user_id, season = row.user_id, seasons.of(row.started_date)
    db.delete(row)
    db.commit()
    _recheck_achievements(background_tasks, user_id, [season])
    return {"message": "Entrada eliminada"}


# ── Ratings (game_scores) ───────────────────────────────────────


def _score_out(s: models.GameScore, user_name: Optional[str], game_name: Optional[str]) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "user": user_name,
        "game_id": s.game_id,
        "game": game_name,
        "score": s.score,
        "updated_at": s.updated_at,
    }


@router.get("/scores")
def list_scores(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    sort: str = Query("updated", pattern="^(user|game|score|updated)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.GameScore, models.User.username, models.Game.name)
        .outerjoin(models.User, models.User.id == models.GameScore.user_id)
        .outerjoin(models.Game, models.Game.id == models.GameScore.game_id)
    )
    if user_id is not None:
        q = q.filter(models.GameScore.user_id == user_id)
    if game_id:
        q = q.filter(models.GameScore.game_id == game_id)
    total = q.count()
    columns = {
        "user": models.User.username,
        "game": models.Game.name,
        "score": models.GameScore.score,
        "updated": models.GameScore.updated_at,
    }
    rows = ordered(q, columns[sort], order, models.GameScore.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_score_out(s, un, gn) for s, un, gn in rows]}


class ScoreCreate(BaseModel):
    user_id: int
    game_id: str
    score: int = Field(ge=1, le=100)


@router.post("/scores", status_code=201)
def create_score(body: ScoreCreate, db: Session = Depends(get_db)):
    """Rate a game on behalf of a player (a user rates a game once)."""
    get_or_404(db, models.User, body.user_id, "Usuario")
    get_or_404(db, models.Game, body.game_id, "Juego")
    row = models.GameScore(user_id=body.user_id, game_id=body.game_id, score=body.score)
    db.add(row)
    commit(db, "Puntuación")
    db.refresh(row)
    return _score_out(row, None, None)


class ScorePatch(BaseModel):
    score: int = Field(ge=1, le=100)


@router.patch("/scores/{row_id}")
def patch_score(row_id: int, body: ScorePatch, db: Session = Depends(get_db)):
    row = get_or_404(db, models.GameScore, row_id, "Puntuación")
    row.score = body.score
    commit(db, "Puntuación")
    db.refresh(row)
    return _score_out(row, None, None)


@router.delete("/scores/{row_id}")
def delete_score(row_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, models.GameScore, row_id, "Puntuación")
    db.delete(row)
    db.commit()
    return {"message": "Puntuación eliminada"}

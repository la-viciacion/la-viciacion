"""Games: list with usage, edit, resync one and delete."""
import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from ...auth import get_db
from ...database import models
from ...utils import hltb_sync, messages, rawg_sync
from ...utils.redaction import redact_rawg_key
from .common import commit, confirm_or_409, get_or_404, like, router


class GamePatch(BaseModel):
    name: Optional[str] = None
    dev: Optional[str] = None
    release_date: Optional[datetime.date] = None
    steam_id: Optional[str] = None
    image_url: Optional[str] = None
    genres: Optional[str] = None
    tags: Optional[str] = None
    avg_time: Optional[int] = None
    slug: Optional[str] = None
    rawg_id: Optional[int] = None
    is_dlc: Optional[bool] = None
    parent_game_id: Optional[str] = None


def _game_out(g: models.Game, sessions: int = 0, players: int = 0, played_seconds: int = 0, parent_name: str | None = None) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "dev": g.dev,
        "release_date": g.release_date,
        "steam_id": g.steam_id,
        "image_url": g.image_url,
        "genres": g.genres,
        "tags": g.tags,
        "avg_time": g.avg_time,
        "slug": g.slug,
        "rawg_id": g.rawg_id,
        "is_dlc": bool(g.is_dlc),
        "parent_game_id": g.parent_game_id,
        "parent_name": parent_name,
        "sessions": sessions,
        "players": players,
        "played_seconds": int(played_seconds or 0),
    }


@router.get("/games")
def list_games(
    search: Optional[str] = None,
    rawg: Optional[str] = Query(None, pattern="^(unlinked|pending)$"),
    sort: str = Query("name", pattern="^(name|release_date|played|players)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Games with their usage (sessions, time played and players). `rawg=unlinked`: no RAWG id;
    `rawg=pending`: what the RAWG sync would try (no id, or basic info missing)."""
    session_counts = (
        db.query(
            models.GameTimer.game_id.label("gid"),
            func.count(models.GameTimer.id).label("n"),
            func.coalesce(func.sum(models.GameTimer.duration_seconds), 0).label("secs"),
        )
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
    played = func.coalesce(session_counts.c.secs, 0)
    base = aliased(models.Game)
    q = (
        db.query(models.Game, sessions.label("sessions"), players.label("players"), played.label("played"), base.name.label("parent_name"))
        .outerjoin(session_counts, session_counts.c.gid == models.Game.id)
        .outerjoin(player_counts, player_counts.c.gid == models.Game.id)
        .outerjoin(base, base.id == models.Game.parent_game_id)
    )
    if search:
        q = q.filter(models.Game.name.like(like(search)))
    if rawg == "unlinked":
        q = q.filter(models.Game.rawg_id.is_(None))
    elif rawg == "pending":
        q = q.filter(rawg_sync.pending_condition())
    total = q.count()
    column = {"name": models.Game.name, "release_date": models.Game.release_date, "played": played, "players": players}[sort]
    direction = column.desc() if order == "desc" else column.asc()
    rows = q.order_by(direction, models.Game.name, models.Game.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_game_out(g, s, p, t, parent) for g, s, p, t, parent in rows]}


@router.patch("/games/{game_id}")
def patch_game(game_id: str, body: GamePatch, db: Session = Depends(get_db)):
    game = get_or_404(db, models.Game, game_id, "Juego")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    if data.get("is_dlc") is None:
        data.pop("is_dlc", None)  # the column is NOT NULL: no value is "leave it"
    _check_parent(db, game, data)
    for k, v in data.items():
        setattr(game, k, v)
    commit(db, "Juego")
    base = db.get(models.Game, game.parent_game_id) if game.parent_game_id else None
    return _game_out(game, parent_name=base.name if base else None)


def _check_parent(db: Session, game: models.Game, data: dict) -> None:
    """The base game must exist and must not lead back to this one; naming one makes the game a DLC and a game
    that is not a DLC has none (`data` is completed accordingly)."""
    parent_id = data.get("parent_game_id")
    if parent_id is not None:
        seen, step = {game.id}, db.get(models.Game, parent_id)
        if step is None:
            raise HTTPException(status_code=400, detail=messages.GAME_PARENT_NOT_FOUND)
        while step is not None:
            if step.id in seen:
                raise HTTPException(status_code=400, detail=messages.GAME_PARENT_LOOP)
            seen.add(step.id)
            step = db.get(models.Game, step.parent_game_id) if step.parent_game_id else None
        data.setdefault("is_dlc", True)
    if data.get("is_dlc") is False:
        data["parent_game_id"] = None


@router.post("/games/{game_id}/resync")
def resync_game(game_id: str, db: Session = Depends(get_db)):
    """Refresh one game from RAWG (metadata) and HLTB (average time). Each source reports on its own, so one
    failing does not stop the other; RAWG goes first because HLTB tells same-named games apart by release year."""
    get_or_404(db, models.Game, game_id, "Juego")
    out = {}
    for source, sync in (("rawg", rawg_sync), ("hltb", hltb_sync)):
        try:
            out[source] = sync.resync_one(db, game_id)
        except (ConnectionError, RuntimeError, rawg_sync.RawgFatal) as e:
            db.rollback()
            out[source] = {"status": "error", "error": redact_rawg_key(str(e))}
    return out


def _game_counts(db: Session, game_id: str) -> dict:
    return {
        "sesiones": db.query(models.GameTimer).filter_by(game_id=game_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(game_id=game_id).count(),
        "logros": db.query(models.UserAchievement).filter_by(game_id=game_id).count(),
        "puntuaciones": db.query(models.GameScore).filter_by(game_id=game_id).count(),
        "deseados": db.query(models.UserWishlist).filter_by(game_id=game_id).count(),
    }


@router.delete("/games/{game_id}")
def delete_game(game_id: str, force: bool = False, db: Session = Depends(get_db)):
    game = get_or_404(db, models.Game, game_id, "Juego")
    confirm_or_409(_game_counts(db, game_id), force)
    db.query(models.GameTimer).filter_by(game_id=game_id).delete()
    db.query(models.UserGame).filter_by(game_id=game_id).delete()
    db.query(models.GameScore).filter_by(game_id=game_id).delete()
    db.query(models.UserWishlist).filter_by(game_id=game_id).delete()
    db.query(models.UserAchievement).filter_by(game_id=game_id).delete()
    db.delete(game)
    db.commit()
    return {"message": "Juego eliminado"}

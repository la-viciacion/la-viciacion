"""Games: list with usage, edit, resync one and delete."""
import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from ...auth import get_db
from ...database import models
from ...clients import igdb
from ...crud.wishlist import is_upcoming
from ...utils import hltb_sync, igdb_sync, messages, rawg_sync
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
    igdb_id: Optional[int] = None
    igdb_slug: Optional[str] = None
    themes: Optional[str] = None
    franchises: Optional[str] = None
    collections: Optional[str] = None
    is_dlc: Optional[bool] = None
    parent_game_id: Optional[str] = None


def _game_out(
    g: models.Game, sessions: int = 0, players: int = 0, parent_name: str | None = None, wishes: int = 0, unused: bool = False,
    upcoming: bool = False,
) -> dict:
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
        "igdb_id": g.igdb_id,
        "igdb_slug": g.igdb_slug,
        "themes": g.themes,
        "franchises": g.franchises,
        "collections": g.collections,
        "is_dlc": bool(g.is_dlc),
        "parent_game_id": g.parent_game_id,
        "parent_name": parent_name,
        "sessions": sessions,
        "players": players,
        "wishes": wishes,
        "unused": unused,
        "upcoming": upcoming,
    }


def _unused_condition():
    """Nothing refers to the game: no session, library entry, wish, rating, achievement, price, challenge or DLC. A game
    that is only wished for (an upcoming release, say) is not unused: it will have sessions and players once it is out."""
    dlc = aliased(models.Game)
    return and_(*(
        ~select(1).where(column == models.Game.id).exists()
        for column in (
            models.GameTimer.game_id, models.UserGame.game_id, models.UserWishlist.game_id, models.GameScore.game_id,
            models.UserAchievement.game_id, models.UserGamePrice.game_id, models.Challenge.game_id, dlc.parent_game_id,
        )
    ))


@router.get("/games")
def list_games(
    search: Optional[str] = None,
    data: Optional[str] = Query(None, pattern="^(unlinked|pending)$"),
    usage: Optional[str] = Query(None, pattern="^(unused|wished|unplayed)$"),
    sort: str = Query("name", pattern="^(name|release_date|sessions|players|wishes)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Games with their usage (sessions, players and wishes). `data=unlinked`: no IGDB id;
    `data=pending`: what the RAWG sync would try (no id, or basic info missing). `usage=unused`: nothing refers to the game
    (safe to delete); `wished`: no sessions and no players but somebody wishes for it (waiting for its release);
    `unplayed`: no sessions and no players, whatever else refers to it."""
    session_counts = (
        db.query(
            models.GameTimer.game_id.label("gid"),
            func.count(models.GameTimer.id).label("n"),
        )
        .group_by(models.GameTimer.game_id)
        .subquery()
    )
    player_counts = (
        db.query(models.UserGame.game_id.label("gid"), func.count(func.distinct(models.UserGame.user_id)).label("n"))
        .group_by(models.UserGame.game_id)
        .subquery()
    )
    wish_counts = (
        db.query(models.UserWishlist.game_id.label("gid"), func.count(models.UserWishlist.id).label("n"))
        .group_by(models.UserWishlist.game_id)
        .subquery()
    )
    sessions = func.coalesce(session_counts.c.n, 0)
    players = func.coalesce(player_counts.c.n, 0)
    wishes = func.coalesce(wish_counts.c.n, 0)
    unused = _unused_condition()
    base = aliased(models.Game)
    q = (
        db.query(
            models.Game, sessions.label("sessions"), players.label("players"), base.name.label("parent_name"),
            wishes.label("wishes"), unused.label("unused"),
        )
        .outerjoin(session_counts, session_counts.c.gid == models.Game.id)
        .outerjoin(player_counts, player_counts.c.gid == models.Game.id)
        .outerjoin(wish_counts, wish_counts.c.gid == models.Game.id)
        .outerjoin(base, base.id == models.Game.parent_game_id)
    )
    if usage == "unused":
        q = q.filter(unused)
    elif usage == "wished":
        q = q.filter(sessions == 0, players == 0, wishes > 0)
    elif usage == "unplayed":
        q = q.filter(sessions == 0, players == 0)
    if search:
        q = q.filter(models.Game.name.like(like(search)))
    if data == "unlinked":
        q = q.filter(models.Game.igdb_id.is_(None))
    elif data == "pending":
        q = q.filter(rawg_sync.pending_condition())
    total = q.count()
    column = {"name": models.Game.name, "release_date": models.Game.release_date, "sessions": sessions, "players": players, "wishes": wishes}[sort]
    direction = column.desc() if order == "desc" else column.asc()
    rows = q.order_by(direction, models.Game.name, models.Game.id).limit(limit).offset(offset).all()
    today = datetime.date.today()
    return {"total": total, "items": [
        _game_out(g, s, p, parent, w, bool(u), is_upcoming(g.release_date, today)) for g, s, p, parent, w, u in rows
    ]}


@router.get("/games/{game_id}/people")
def game_people(game_id: str, db: Session = Depends(get_db)):
    """Who has the game in their library (with the platforms and seasons of their entries) and who wishes for it, every
    account whatever its state: it is what deleting the game would take away."""
    get_or_404(db, models.Game, game_id, "Juego")
    owners: dict[int, dict] = {}
    entries = (
        db.query(models.UserGame.user_id, models.UserGame.platform, models.UserGame.season, models.User.username, models.User.name, models.User.is_active)
        .join(models.User, models.User.id == models.UserGame.user_id)
        .filter(models.UserGame.game_id == game_id)
        .order_by(models.UserGame.season.desc())
    )
    for user_id, platform, season, username, name, active in entries:
        person = owners.setdefault(user_id, {"user_id": user_id, "username": username, "name": name or username, "is_active": bool(active), "entries": []})
        person["entries"].append({"platform": platform, "season": season})
    wishes = (
        db.query(models.User.id, models.User.username, models.User.name, models.User.is_active, models.UserWishlist.added_at)
        .join(models.UserWishlist, models.UserWishlist.user_id == models.User.id)
        .filter(models.UserWishlist.game_id == game_id)
        .order_by(models.UserWishlist.added_at, models.User.id)
    )
    return {
        "players": sorted(owners.values(), key=lambda p: p["name"].lower()),
        "wishes": [
            {"user_id": user_id, "username": username, "name": name or username, "is_active": bool(active), "added_at": added_at}
            for user_id, username, name, active, added_at in wishes
        ],
    }


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
    """Refresh one game from RAWG and IGDB (metadata) and HLTB (average time). Each source reports on its own, so one
    failing does not stop the others. RAWG goes before IGDB (what IGDB gives wins, it is the main source) and both before
    HLTB, which tells same-named games apart by release year."""
    get_or_404(db, models.Game, game_id, "Juego")
    out = {}
    for source, sync in (("rawg", rawg_sync), ("igdb", igdb_sync), ("hltb", hltb_sync)):
        try:
            out[source] = sync.resync_one(db, game_id)
        except (ConnectionError, RuntimeError, rawg_sync.RawgFatal, igdb.IgdbError) as e:
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

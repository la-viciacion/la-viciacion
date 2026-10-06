"""The wishlist: the games a player wants to play, among them the ones that are not released yet.

Only the wish is stored (`users_wishlist`). Whether a game is upcoming, whether a wish is still pending
(the game is not in the player's library yet: once they play it, it leaves the list by itself) and who else
wants a game are derived when asked. Only active players count (never the emergency account)."""
import datetime

from sqlalchemy import exists
from sqlalchemy.orm import Session

from ..database import models
from . import games


def is_upcoming(release_date: datetime.date | None, today: datetime.date) -> bool:
    """A game without a date counts as not released yet: RAWG lists the announced games with none (TBA)."""
    return release_date is None or release_date > today


def days_until(release_date: datetime.date | None, today: datetime.date) -> int | None:
    """0 when it comes out today; None without a date or once it is out."""
    return None if release_date is None or release_date < today else (release_date - today).days


def _pending():
    """Condition on a wish: the player does not have the game in their library (any season or platform)."""
    in_library = exists().where(
        models.UserGame.user_id == models.UserWishlist.user_id,
        models.UserGame.game_id == models.UserWishlist.game_id,
    )
    return ~in_library


def add(db: Session, user_id: int, game_id: str) -> None:
    """Wish for a game (nothing happens if it already is wished). Not committed."""
    if not db.query(models.UserWishlist.id).filter_by(user_id=user_id, game_id=game_id).first():
        db.add(models.UserWishlist(user_id=user_id, game_id=game_id))


def remove(db: Session, user_id: int, game_id: str) -> None:
    """Drop the wish (nothing happens if there is none). Not committed."""
    db.query(models.UserWishlist).filter_by(user_id=user_id, game_id=game_id).delete()


def in_library(db: Session, user_id: int, game_id: str) -> bool:
    return db.query(models.UserGame.id).filter_by(user_id=user_id, game_id=game_id).first() is not None


def wished_ids(db: Session, user_id: int) -> set[str]:
    """The games the user wants and does not have yet."""
    rows = db.query(models.UserWishlist.game_id).filter(models.UserWishlist.user_id == user_id, _pending())
    return {game_id for (game_id,) in rows}


def wanters(db: Session, game_ids: list[str], exclude_user_id: int | None = None) -> dict[str, list[dict]]:
    """game_id -> the players of the group who want it and do not have it, by name."""
    found: dict[str, list[dict]] = {}
    if not game_ids:
        return found
    query = (
        db.query(models.UserWishlist.game_id, models.User.id, models.User.username, models.User.name)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(
            models.UserWishlist.game_id.in_(game_ids),
            models.User.is_active == 1,
            models.not_god(),
            _pending(),
        )
        .order_by(models.UserWishlist.added_at, models.User.id)
    )
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)
    for game_id, user_id, username, name in query:
        found.setdefault(game_id, []).append({"user_id": user_id, "username": username, "name": name or username})
    return found


def wishlist(db: Session, viewer_id: int, today: datetime.date) -> dict:
    """The viewer's list in two parts: `upcoming` (not released: the nearest first, the ones without a date last)
    and `wanted` (released: the latest wish first), each game with the other players who want it."""
    rows = (
        db.query(models.UserWishlist.added_at, models.Game)
        .join(models.Game, models.UserWishlist.game_id == models.Game.id)
        .filter(models.UserWishlist.user_id == viewer_id, _pending())
        .all()
    )
    others = wanters(db, [game.id for _, game in rows], exclude_user_id=viewer_id)
    upcoming, wanted = [], []
    for added_at, game in rows:
        item = {
            "id": game.id,
            "name": game.name,
            "image_url": game.image_url,
            "genres": games.genre_list(game.genres),
            "release_date": game.release_date,
            "days_until": days_until(game.release_date, today),
            "added_at": added_at,
            "wanted_by": others.get(game.id, []),
        }
        (upcoming if is_upcoming(game.release_date, today) else wanted).append(item)
    upcoming.sort(key=lambda g: (g["release_date"] is None, g["release_date"] or datetime.date.max, (g["name"] or "").lower()))
    wanted.sort(key=lambda g: (-g["added_at"].timestamp(), (g["name"] or "").lower()))
    return {"upcoming": upcoming, "wanted": wanted}


def to_refresh(db: Session, today: datetime.date) -> list[models.Game]:
    """Games somebody is waiting for whose release date may still change: not released (or releasing today) and
    known to RAWG, which is where a date is refreshed from."""
    return (
        db.query(models.Game)
        .join(models.UserWishlist, models.UserWishlist.game_id == models.Game.id)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(
            models.Game.rawg_id.isnot(None),
            (models.Game.release_date.is_(None)) | (models.Game.release_date >= today),
            models.User.is_active == 1,
            models.not_god(),
            _pending(),
        )
        .distinct()
        .all()
    )


def wished_releases_on(db: Session, day: datetime.date) -> list[tuple[models.Game, list[str]]]:
    """The games that come out on `day` that somebody still waits for, with the names of those players."""
    game_ids = [
        game_id
        for (game_id,) in db.query(models.Game.id)
        .join(models.UserWishlist, models.UserWishlist.game_id == models.Game.id)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(models.Game.release_date == day, models.User.is_active == 1, models.not_god(), _pending())
        .distinct()
    ]
    waiting = wanters(db, game_ids)
    games_by_id = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_(game_ids))}
    found = [(games_by_id[game_id], [w["name"] for w in waiting[game_id]]) for game_id in game_ids]
    return sorted(found, key=lambda item: (item[0].name or "").lower())


def releases_on(db: Session, day: datetime.date) -> list[tuple[models.User, models.Game, list[dict]]]:
    """Who is waiting for a game that comes out on `day`: (player, game, the other players who want it too)."""
    rows = (
        db.query(models.User, models.Game)
        .join(models.UserWishlist, models.UserWishlist.user_id == models.User.id)
        .join(models.Game, models.UserWishlist.game_id == models.Game.id)
        .filter(models.Game.release_date == day, models.User.is_active == 1, models.not_god(), _pending())
        .order_by(models.User.id, models.Game.name)
        .all()
    )
    everyone = wanters(db, list({game.id for _, game in rows}))
    return [(user, game, [w for w in everyone.get(game.id, []) if w["user_id"] != user.id]) for user, game in rows]

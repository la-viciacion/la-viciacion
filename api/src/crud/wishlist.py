"""The wishlist: the games a player wants to play, among them the ones that are not released yet.

Only the wish is stored (`users_wishlist`). Whether a game is upcoming, whether it is in the player's library and
who else wants it are derived when asked. A wish stays until the player removes it, played or not (an early access,
say). Only active players count (never the emergency account)."""
import datetime

from sqlalchemy.orm import Session

from ..database import models
from . import games


def is_upcoming(release_date: datetime.date | None, today: datetime.date) -> bool:
    """A game without a date counts as not released yet: RAWG lists the announced games with none (TBA)."""
    return release_date is None or release_date > today


def days_until(release_date: datetime.date | None, today: datetime.date) -> int | None:
    """0 when it comes out today; None without a date or once it is out."""
    return None if release_date is None or release_date < today else (release_date - today).days


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
    """The games the user wants."""
    rows = db.query(models.UserWishlist.game_id).filter(models.UserWishlist.user_id == user_id)
    return {game_id for (game_id,) in rows}


def wanters(db: Session, game_ids: list[str], exclude_user_id: int | None = None) -> dict[str, list[dict]]:
    """game_id -> the players of the group who want it, by name."""
    found: dict[str, list[dict]] = {}
    if not game_ids:
        return found
    query = (
        db.query(models.UserWishlist.game_id, models.User.id, models.User.username, models.User.name)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(models.UserWishlist.game_id.in_(game_ids), models.User.is_active == 1, models.not_god())
        .order_by(models.UserWishlist.added_at, models.User.id)
    )
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)
    for game_id, user_id, username, name in query:
        found.setdefault(game_id, []).append({"user_id": user_id, "username": username, "name": name or username})
    return found


def wishlist(db: Session, viewer_id: int, today: datetime.date) -> dict:
    """The viewer's list in two parts: `upcoming` (not released: the nearest first, the ones without a date last)
    and `wanted` (released: the latest wish first), each game with the other players who want it and whether it
    already is in the viewer's library."""
    rows = (
        db.query(models.UserWishlist.added_at, models.Game)
        .join(models.Game, models.UserWishlist.game_id == models.Game.id)
        .filter(models.UserWishlist.user_id == viewer_id)
        .all()
    )
    others = wanters(db, [game.id for _, game in rows], exclude_user_id=viewer_id)
    owned = {game_id for (game_id,) in db.query(models.UserGame.game_id).filter(models.UserGame.user_id == viewer_id)}
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
            "in_library": game.id in owned,
            "wanted_by": others.get(game.id, []),
        }
        (upcoming if is_upcoming(game.release_date, today) else wanted).append(item)
    upcoming.sort(key=lambda g: (g["release_date"] is None, g["release_date"] or datetime.date.max, (g["name"] or "").lower()))
    wanted.sort(key=lambda g: (-g["added_at"].timestamp(), (g["name"] or "").lower()))
    return {"upcoming": upcoming, "wanted": wanted}


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    """First and last day of a month."""
    first = datetime.date(year, month, 1)
    following = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return first, following - datetime.timedelta(days=1)


def releases(db: Session, viewer_id: int, year: int, month: int, today: datetime.date) -> dict:
    """The release calendar of the group: every game of the catalogue that comes out in the month, wanted or not,
    out already or not, by date, and apart the games somebody wants that have
    no date yet (the undated ones nobody wants are most of the catalogue, and not upcoming). Each comes with
    everybody who wants it, the viewer included (`is_me`), and nobody if none does. Derived; only the wishes are stored."""
    first, last = month_bounds(year, month)
    wished = (
        db.query(models.UserWishlist.game_id)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(models.User.is_active == 1, models.not_god())
    )
    rows = (
        db.query(models.Game)
        .filter(
            models.Game.release_date.between(first, last)
            | (models.Game.release_date.is_(None) & models.Game.id.in_(wished))
        )
        .all()
    )
    everyone = wanters(db, [game.id for game in rows])
    items = [
        {
            "id": game.id,
            "name": game.name,
            "image_url": game.image_url,
            "genres": games.genre_list(game.genres),
            "release_date": game.release_date,
            "days_until": days_until(game.release_date, today),
            "wanted_by": [{**w, "is_me": w["user_id"] == viewer_id} for w in everyone.get(game.id, [])],
        }
        for game in rows
    ]
    items.sort(key=lambda g: (g["release_date"] or datetime.date.max, (g["name"] or "").lower()))
    return {
        "month": f"{year:04d}-{month:02d}",
        "releases": [g for g in items if g["release_date"]],
        "undated": [g for g in items if not g["release_date"]],
    }


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
        )
        .distinct()
        .all()
    )


def wished_releases_between(db: Session, first: datetime.date, last: datetime.date) -> list[tuple[models.Game, list[str]]]:
    """The games that come out from `first` to `last` (both included) that somebody wished, with the names of those
    players, by date and then by name."""
    game_ids = [
        game_id
        for (game_id,) in db.query(models.Game.id)
        .join(models.UserWishlist, models.UserWishlist.game_id == models.Game.id)
        .join(models.User, models.UserWishlist.user_id == models.User.id)
        .filter(models.Game.release_date.between(first, last), models.User.is_active == 1, models.not_god())
        .distinct()
    ]
    waiting = wanters(db, game_ids)
    games_by_id = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_(game_ids))}
    found = [(games_by_id[game_id], [w["name"] for w in waiting[game_id]]) for game_id in game_ids]
    return sorted(found, key=lambda item: (item[0].release_date, (item[0].name or "").lower()))


def releases_on(db: Session, day: datetime.date) -> list[tuple[models.User, models.Game, list[dict]]]:
    """Who is waiting for a game that comes out on `day`: (player, game, the other players who want it too)."""
    rows = (
        db.query(models.User, models.Game)
        .join(models.UserWishlist, models.UserWishlist.user_id == models.User.id)
        .join(models.Game, models.UserWishlist.game_id == models.Game.id)
        .filter(models.Game.release_date == day, models.User.is_active == 1, models.not_god())
        .order_by(models.User.id, models.Game.name)
        .all()
    )
    everyone = wanters(db, list({game.id for _, game in rows}))
    return [(user, game, [w for w in everyone.get(game.id, []) if w["user_id"] != user.id]) for user, game in rows]

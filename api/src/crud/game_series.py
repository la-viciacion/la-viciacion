"""The saga of a game: the games of its RAWG series in order of release, each with what the viewer and the group have of it.
Derived from RAWG's series (utils/rawg_series.py, cached in memory) and the libraries when asked; nothing is stored."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models


def order(rows: list[dict]) -> list[dict]:
    """By release date, the ones without a date last, then by name (pure)."""
    return sorted(rows, key=lambda r: (r["released"] is None, r["released"] or "", r["name"].lower()))


def mark_next(rows: list[dict]) -> list[dict]:
    """Flag `next` on the first game released after the current one that the viewer has not completed (pure; rows in
    order). Nothing is flagged when the current game has no release date or is the last of the saga."""
    current = next((r for r in rows if r["current"]), None)
    if current is None or not current["released"]:
        return rows
    for row in rows:
        row["next"] = False
    for row in rows:
        if row["released"] and row["released"] > current["released"] and not (row["mine"] and row["mine"]["completed"]):
            row["next"] = True
            break
    return rows


def saga(db: Session, game: models.Game, viewer_id: int, series: list[dict]) -> list[dict]:
    """The series of `game` (RAWG's other games) plus the game itself, with, for each one the catalogue has, the viewer's
    status (`mine`: has it, completed it, seconds played) and how many players have it."""
    others = [s for s in series if s["rawg_id"] != game.rawg_id]
    if not others:
        return []
    ids = [s["rawg_id"] for s in others]
    in_catalogue = {g.rawg_id: g for g in db.query(models.Game).filter(models.Game.rawg_id.in_(ids))}
    game_ids = [g.id for g in in_catalogue.values()] + [game.id]
    owners = {
        game_id: count
        for game_id, count in db.query(models.UserGame.game_id, func.count(func.distinct(models.UserGame.user_id)))
        .join(models.User, models.User.id == models.UserGame.user_id)
        .filter(models.UserGame.game_id.in_(game_ids), models.not_god())
        .group_by(models.UserGame.game_id)
    }
    mine = {
        game_id: {"has": True, "completed": bool(completed)}
        for game_id, completed in db.query(models.UserGame.game_id, func.max(models.UserGame.completed))
        .filter(models.UserGame.user_id == viewer_id, models.UserGame.game_id.in_(game_ids))
        .group_by(models.UserGame.game_id)
    }
    seconds = {
        game_id: int(total or 0)  # MariaDB returns SUM() as Decimal
        for game_id, total in db.query(models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds))
        .filter(models.GameTimer.user_id == viewer_id, models.GameTimer.game_id.in_(game_ids), models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.game_id)
    }

    def row(name, released, image_url, slug, rawg_id, found: models.Game | None, current: bool) -> dict:
        status = dict(mine[found.id], seconds=seconds.get(found.id, 0)) if found is not None and found.id in mine else None
        return {
            "rawg_id": rawg_id, "name": name, "slug": slug, "image_url": image_url, "released": released,
            "game_id": found.id if found is not None else None, "current": current, "next": False,
            "mine": status, "players": owners.get(found.id, 0) if found is not None else 0,
        }

    rows = [row(game.name, game.release_date.isoformat() if game.release_date else None, game.image_url, game.slug or None, game.rawg_id, game, True)]
    for s in others:
        found = in_catalogue.get(s["rawg_id"])
        rows.append(row(found.name if found else s["name"], s["released"], (found.image_url if found else None) or s["image_url"], s["slug"], s["rawg_id"], found, False))
    return mark_next(order(rows))

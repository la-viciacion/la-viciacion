"""What the group has done with one game: who has it, their hours, completions and ratings.

Everything here is derived from the library, the sessions and the ratings when asked; nothing is stored.
Every player counts, active or not (never the emergency account), like the rankings and the recommendations."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import games, time_entries, wishlist


def overview(db: Session, game_id: str, viewer_id: int) -> dict | None:
    """The game and the players who have it (any season), the most played first; None if there is no such game."""
    game = db.get(models.Game, game_id)
    if game is None:
        return None
    players = (models.not_god(),)

    entries: dict[int, dict] = {}
    for user_id, username, name, is_active, season, completed in (
        db.query(
            models.UserGame.user_id, models.User.username, models.User.name, models.User.is_active,
            models.UserGame.season, models.UserGame.completed,
        )
        .join(models.User, models.UserGame.user_id == models.User.id)
        .filter(models.UserGame.game_id == game_id, *players)
        .all()
    ):
        player = entries.setdefault(
            user_id,
            {"user_id": user_id, "username": username, "name": name or username, "is_active": bool(is_active), "seasons": set(), "completions": set()},
        )
        player["seasons"].add(season)
        if completed:
            player["completions"].add(season)

    played = {
        user_id: (int(seconds or 0), sessions, last)  # MariaDB returns SUM() as Decimal
        for user_id, seconds, sessions, last in db.query(
            models.GameTimer.user_id,
            func.sum(models.GameTimer.duration_seconds),
            func.count(models.GameTimer.id),
            func.max(models.GameTimer.start_time),
        )
        .filter(models.GameTimer.game_id == game_id, models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.user_id)
    }
    scores = dict(
        db.query(models.GameScore.user_id, models.GameScore.score)
        .join(models.User, models.GameScore.user_id == models.User.id)
        .filter(models.GameScore.game_id == game_id, *players)
        .all()
    )
    # a stale timer is more likely forgotten than played, and who hides is not listed (see get_now_playing)
    playing_now = {p["user_id"] for p in time_entries.get_now_playing(db, viewer_id) if p["game_id"] == game_id and not p["stale"]}

    rows = []
    for user_id, player in entries.items():
        seconds, sessions, last = played.get(user_id, (0, 0, None))
        rows.append({
            "user_id": user_id,
            "username": player["username"],
            "name": player["name"],
            "is_active": player["is_active"],
            "played_seconds": seconds,
            "sessions": sessions,
            "last_played": last,
            "seasons": sorted(player["seasons"], reverse=True),
            "completed": bool(player["completions"]),
            "completions": len(player["completions"]),
            "score": scores.get(user_id),
            "playing": user_id in playing_now,
            "is_me": user_id == viewer_id,
        })
    rows.sort(key=lambda r: (-r["played_seconds"], r["name"].lower()))

    wished = wishlist.wished_ids(db, viewer_id)
    rated = [r["score"] for r in rows if r["score"] is not None]
    return {
        "game": {
            "id": game.id,
            "name": game.name,
            "image_url": game.image_url,
            "genres": games.genre_list(game.genres),
            "dev": game.dev,
            "release_date": game.release_date,
            "avg_time": game.avg_time or None,
        },
        "summary": {
            "players": len(rows),
            "played_seconds": sum(r["played_seconds"] for r in rows),
            "completed_by": sum(1 for r in rows if r["completed"]),
            "score_count": len(rated),
            "score_mean": round(sum(rated) / len(rated), 1) if rated else None,
        },
        "players": rows,
        "wished": game_id in wished,
        "wanted_by": wishlist.wanters(db, [game_id], exclude_user_id=viewer_id).get(game_id, []),
    }

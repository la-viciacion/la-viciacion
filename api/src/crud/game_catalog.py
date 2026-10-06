"""The catalog of games for the Juegos page: every game with what the group has done with it, filtered, ordered
and paged. Derived from the library, the sessions and the ratings when asked; nothing is stored. Only active
players count (never the emergency account)."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import games, time_entries, wishlist

SORTS = ("activity", "played", "rated", "players", "release", "name")


def _none_last(value, missing):
    """Sort key part that puts the games without a value after the ones that have it."""
    return (value is None, missing if value is None else value)


def catalog(
    db: Session,
    viewer_id: int,
    *,
    q: str | None = None,
    genre: str | None = None,
    library: str | None = None,
    completed: bool = False,
    rated: bool = False,
    playing: bool = False,
    with_players: bool = False,
    sort: str = "activity",
    limit: int = 30,
    offset: int = 0,
) -> dict:
    """`library`: "have" (in the viewer's library) or "not". `completed` / `rated`: by the viewer.
    `playing`: somebody is playing it right now. `with_players`: at least one player has it."""
    players = (models.User.is_active == 1, models.not_god())

    owners: dict[str, set[int]] = {}
    completers: dict[str, set[int]] = {}
    started: dict[str, datetime.date] = {}
    for game_id, user_id, done, day in (
        db.query(models.UserGame.game_id, models.UserGame.user_id, models.UserGame.completed, models.UserGame.started_date)
        .join(models.User, models.UserGame.user_id == models.User.id)
        .filter(*players)
    ):
        owners.setdefault(game_id, set()).add(user_id)
        if done:
            completers.setdefault(game_id, set()).add(user_id)
        if day and (game_id not in started or day > started[game_id]):
            started[game_id] = day

    played = {
        game_id: (int(seconds or 0), last)  # MariaDB returns SUM() as Decimal
        for game_id, seconds, last in db.query(
            models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds), func.max(models.GameTimer.start_time)
        )
        .join(models.User, models.GameTimer.user_id == models.User.id)
        .filter(*players)
        .group_by(models.GameTimer.game_id)
    }
    ratings = {
        game_id: (count, float(mean))
        for game_id, count, mean in db.query(models.GameScore.game_id, func.count(models.GameScore.id), func.avg(models.GameScore.score))
        .join(models.User, models.GameScore.user_id == models.User.id)
        .filter(*players)
        .group_by(models.GameScore.game_id)
    }
    my_scores = dict(db.query(models.GameScore.game_id, models.GameScore.score).filter_by(user_id=viewer_id).all())
    wished = wishlist.wished_ids(db, viewer_id)
    live = {p["game_id"] for p in time_entries.get_now_playing(db, viewer_id) if not p["stale"]}

    wanted = (q or "").strip().lower()
    genre_filter = (genre or "").strip().lower()
    every_genre: set[str] = set()
    rows = []
    for game in db.query(models.Game).all():
        genres = games.genre_list(game.genres)
        every_genre.update(genres)
        have = viewer_id in owners.get(game.id, ())
        mine_done = viewer_id in completers.get(game.id, ())
        if wanted and wanted not in (game.name or "").lower():
            continue
        if genre_filter and genre_filter not in (g.lower() for g in genres):
            continue
        if library == "have" and not have or library == "not" and have:
            continue
        if completed and not mine_done or rated and game.id not in my_scores:
            continue
        if playing and game.id not in live or with_players and game.id not in owners:
            continue
        seconds, last_session = played.get(game.id, (0, None))
        count, mean = ratings.get(game.id, (0, None))
        day = started.get(game.id)
        last = max(filter(None, (last_session, day and datetime.datetime.combine(day, datetime.time())))) if (last_session or day) else None
        rows.append({
            "id": game.id,
            "name": game.name,
            "image_url": game.image_url,
            "genres": genres,
            "release_date": game.release_date,
            "players": len(owners.get(game.id, ())),
            "played_seconds": seconds,
            "completed_by": len(completers.get(game.id, ())),
            "score_count": count,
            "score_mean": None if mean is None else round(mean, 1),
            "have": have,
            "wished": game.id in wished,
            "my_score": my_scores.get(game.id),
            "my_completed": mine_done,
            "playing_now": game.id in live,
            "last_activity": last,
            "last_played": last_session,
        })

    name = lambda r: (r["name"] or "").lower()  # noqa: E731
    keys = {
        "activity": lambda r: (_none_last(None if r["last_activity"] is None else -r["last_activity"].timestamp(), 0), name(r)),
        "played": lambda r: (-r["played_seconds"], name(r)),
        "rated": lambda r: (_none_last(None if r["score_mean"] is None else -r["score_mean"], 0), -r["score_count"], name(r)),
        "players": lambda r: (-r["players"], -r["played_seconds"], name(r)),
        "release": lambda r: (_none_last(None if r["release_date"] is None else -r["release_date"].toordinal(), 0), name(r)),
        "name": name,
    }
    rows.sort(key=keys[sort if sort in keys else "activity"])
    return {"total": len(rows), "items": rows[offset:offset + limit], "genres": sorted(every_genre, key=str.lower)}

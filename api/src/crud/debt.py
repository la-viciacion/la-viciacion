"""The debt of each player: how much is left to play, by the average time to complete, in the games they started
and have not finished. Derived from the sessions, the library and the games' average time when asked; nothing is
stored (the time of a library entry is the sum of its sessions, see time_entries.entry_played_time)."""
import datetime
import types

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.orm import Session

from ..database import models
from ..utils import seasons
from . import time_entries, users


def _counted_games(sessions: list, entries: list, avg_times: dict) -> dict:
    """{(user_id, game_id): seconds still to play} for the games that count.

    A game counts when the player has a session of 10 minutes or more in it, it has an average time to complete,
    and it is neither completed nor abandoned. `sessions` are (user_id, game_id, played, long_sessions, last_played)
    of the scope asked for (a season or all of them) and `entries` are (user_id, game_id, completed, abandoned_at)
    of the same scope. A game completed in any season of the scope, or whose every entry is abandoned, is left out."""
    entries_by_game: dict = {}
    for user_id, game_id, completed, abandoned_at in entries:
        entries_by_game.setdefault((user_id, game_id), []).append((completed, abandoned_at))
    counted = {}
    for user_id, game_id, played, long_sessions, last_played in sessions:
        average = avg_times.get(game_id)
        if not average or not long_sessions:
            continue
        own = entries_by_game.get((user_id, game_id), [])
        if any(completed for completed, _ in own):
            continue
        # `is_abandoned` reads only these two fields of an entry
        abandoned = [
            users.is_abandoned(types.SimpleNamespace(completed=completed, abandoned_at=abandoned_at), last_played)
            for completed, abandoned_at in own
        ]
        if own and all(abandoned):
            continue
        counted[(user_id, game_id)] = max(0, average - (played or 0))
    return counted


def user_debt(db: Session, season: int | None = None, is_active: bool | None = None) -> list[dict]:
    """Every player with the seconds they still have to play and the games that account for them, in the
    season (`seasons.ALL` for the whole history), the player with the most debt first."""
    season = seasons.or_current(season)
    sessions = time_entries.sessions_subquery()
    long_session = case((sessions.c.duration >= time_entries.MIN_SESSION_SECONDS, 1), else_=0)
    stmt = select(
        sessions.c.user_id,
        sessions.c.game_id,
        cast(func.sum(sessions.c.duration), Integer),
        cast(func.sum(long_session), Integer),
        func.max(sessions.c.start),
    ).group_by(sessions.c.user_id, sessions.c.game_id)
    entries_stmt = select(
        models.UserGame.user_id, models.UserGame.game_id, models.UserGame.completed, models.UserGame.abandoned_at
    )
    if season != seasons.ALL:
        stmt = stmt.where(sessions.c.season == season)
        entries_stmt = entries_stmt.where(models.UserGame.season == season)
    avg_times = dict(db.execute(select(models.Game.id, models.Game.avg_time).where(models.Game.avg_time > 0)).all())
    counted = _counted_games(
        [tuple(row) for row in db.execute(stmt).all()],
        [tuple(row) for row in db.execute(entries_stmt).all()],
        avg_times,
    )
    totals: dict = {}
    for (user_id, _), remaining in counted.items():
        seconds, games = totals.get(user_id, (0, 0))
        totals[user_id] = (seconds + remaining, games + (1 if remaining else 0))
    players = select(models.User.id, models.User.name).where(models.not_god())
    if is_active is not None:
        players = players.where(models.User.is_active == is_active)
    rows = [
        {"user_id": user_id, "name": name, "debt_time": totals.get(user_id, (0, 0))[0], "games": totals.get(user_id, (0, 0))[1]}
        for user_id, name in db.execute(players).all()
    ]
    rows.sort(key=lambda r: (-r["debt_time"], r["user_id"]))
    return rows


def games_in_debt_at(db: Session, user_id: int, day: datetime.date) -> dict[str, int]:
    """{game_id: seconds still to play} the player had at the start of `day`, over every season: the games they had
    started (a session of 10 minutes or more before it), had not finished and had not abandoned by then, and that
    have an average time. A game already past its average time is there with 0: it is still open. Worked out from
    what happened before `day`, so it does not drift when the averages are synced again."""
    cutoff = datetime.datetime.combine(day, datetime.time.min)
    sessions = time_entries.sessions_subquery()
    long_session = case((sessions.c.duration >= time_entries.MIN_SESSION_SECONDS, 1), else_=0)
    played = db.execute(
        select(
            sessions.c.user_id,
            sessions.c.game_id,
            cast(func.sum(sessions.c.duration), Integer),
            cast(func.sum(long_session), Integer),
            func.max(sessions.c.start),
        )
        .where(sessions.c.user_id == user_id, sessions.c.start < cutoff)
        .group_by(sessions.c.user_id, sessions.c.game_id)
    ).all()
    entries = []
    for game_id, completed, completed_date, abandoned_at in db.execute(
        select(models.UserGame.game_id, models.UserGame.completed, models.UserGame.completed_date, models.UserGame.abandoned_at).where(
            models.UserGame.user_id == user_id
        )
    ):
        finished = bool(completed) and (completed_date is None or completed_date < day)
        entries.append((user_id, game_id, 1 if finished else 0, abandoned_at if abandoned_at is not None and abandoned_at < cutoff else None))
    avg_times = dict(db.execute(select(models.Game.id, models.Game.avg_time).where(models.Game.avg_time > 0)).all())
    counted = _counted_games([tuple(row) for row in played], entries, avg_times)
    return {game_id: seconds for (_, game_id), seconds in counted.items()}

"""The recap ("Wrapped") of a month or a season, derived when asked from the sessions, the library and the
achievements; nothing is stored. A month and a season are the same thing here: a `Period`.

A session counts in the period (and the day) it started in, as everywhere else (`season` is derived from `start_time`).
"""
import datetime
import re
from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from ..utils import streaks
from . import games as games_crud
from . import time_entries

TOP_GAMES = 3
WINDOW_DAYS = 5  # the first days of a month (or of January, for the season) in which a finished recap can be opened
TOP_PLAYER_GAMES = 5
TOP_GENRES = 5
PERIOD_FORMAT = re.compile(r"^(\d{4})(?:-(\d{2}))?$")


@dataclass(frozen=True)
class Period:
    kind: str  # "month" or "year"
    start: datetime.date
    end: datetime.date  # the first day after the period

    @property
    def key(self) -> str:
        return self.start.strftime("%Y-%m" if self.kind == "month" else "%Y")

    @property
    def last_day(self) -> datetime.date:
        return self.end - datetime.timedelta(days=1)

    def previous(self) -> "Period":
        return month_period(*_previous_month(self.start)) if self.kind == "month" else year_period(self.start.year - 1)


def _previous_month(day: datetime.date) -> tuple[int, int]:
    return (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)


def month_period(year: int, month: int) -> Period:
    end = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    return Period("month", datetime.date(year, month, 1), end)


def year_period(year: int) -> Period:
    return Period("year", datetime.date(year, 1, 1), datetime.date(year + 1, 1, 1))


def period_problem(period: Period, today: datetime.date | None = None) -> str | None:
    """Why `period` cannot be viewed yet, or None: "future" (it has not started) or, for a month only, "running"
    (it has started but not finished). A season in progress is a `period_problem` of its own, `season_locked`:
    by default nobody sees it change day by day, only once it is unlocked."""
    today = today or datetime.date.today()
    if period.start > today:
        return "future"
    if period.kind == "month" and period.end > today:
        return "running"
    return None


def season_locked(period: Period, unlocked_year: int, today: datetime.date | None = None) -> bool:
    """Whether the still-running season's recap is locked: visible to nobody until an admin unlocks it (by hand, or
    automatically when its notice reaches the group, see utils.recap_notices.announce_recap) for exactly this year.
    A finished season, or a month, is never locked by this (`period_problem` covers those)."""
    today = today or datetime.date.today()
    return period.kind == "year" and period.end > today and unlocked_year != period.start.year


def recap_closed(period: Period, always_available: bool, today: datetime.date | None = None) -> bool:
    """Whether a finished recap can no longer be opened by a player: it is only there in the first days of the month
    after it (`WINDOW_DAYS`), and in January also the season that ended with December. `always_available` (panel)
    lifts that. The running season is not judged here: `season_locked` already decides it."""
    today = today or datetime.date.today()
    if always_available or period.end > today:
        return False
    if today.day > WINDOW_DAYS:
        return True
    if period.kind == "month":
        return period.end != today.replace(day=1)
    return not (today.month == 1 and period.end == today.replace(day=1))


def parse_period(text: str) -> Period:
    """"2026-09" is a month and "2026" a season. ValueError for anything else."""
    match = PERIOD_FORMAT.match(text or "")
    if not match:
        raise ValueError(text)
    year, month = int(match.group(1)), match.group(2)
    if not 1 <= year <= 9998:
        raise ValueError(text)
    if month is None:
        return year_period(year)
    if not 1 <= int(month) <= 12:
        raise ValueError(text)
    return month_period(year, int(month))


class Played(NamedTuple):
    user_id: int
    game_id: str
    start: datetime.datetime
    end: datetime.datetime | None
    seconds: int


def _sum_by(played: list[Played], key) -> dict:
    totals: dict = {}
    for session in played:
        totals[key(session)] = totals.get(key(session), 0) + session.seconds
    return totals


def _top(totals: dict) -> tuple | None:
    """The (key, seconds) with the most time; the smallest key wins a tie, so the answer never depends on the order."""
    return min(totals.items(), key=lambda item: (-item[1], item[0])) if totals else None


def played_days(played: list[Played], period: Period) -> list[datetime.date]:
    """The days of the period the player played on, by the rule everything else uses (`time_entries.played_days_by_user`):
    a session of 10 minutes or more gives the day it began and the day it ended, as long as they fall in the period."""
    days = set()
    for session in played:
        if session.seconds >= time_entries.MIN_SESSION_SECONDS:
            days.update(day for day in (session.start.date(), session.end.date() if session.end else None) if day and period.start <= day < period.end)
    return sorted(days)


def player_stats(played: list[Played], period: Period) -> dict:
    """What one player did in the period, from their own sessions."""
    days = played_days(played, period)
    star = _top(_sum_by(played, lambda s: s.game_id))
    best_day = _top(_sum_by(played, lambda s: s.start.date()))
    return {
        "seconds": sum(s.seconds for s in played),
        "sessions": len(played),
        "days": len(days),
        "games": len({s.game_id for s in played}),
        "star_game_id": star[0] if star else None,
        "star_game_seconds": star[1] if star else 0,
        "best_day": best_day[0] if best_day else None,
        "best_day_seconds": best_day[1] if best_day else 0,
        "best_streak": streaks.streak_summary(days, period.last_day, period.start.year)[1],
        "longest_session": max((s.seconds for s in played), default=0),
    }


def activity_stats(played: list[Played]) -> dict:
    """When the time was played: seconds by weekday (Monday first), by hour of the day a session started in, and by day.

    A session counts wholly in the weekday, hour and day it started in, as everywhere else in the recap."""
    by_weekday = [0] * 7
    by_hour = [0] * 24
    by_day: dict[str, int] = {}
    for session in played:
        by_weekday[session.start.weekday()] += session.seconds
        by_hour[session.start.hour] += session.seconds
        day = session.start.date().isoformat()
        by_day[day] = by_day.get(day, 0) + session.seconds
    return {"by_weekday": by_weekday, "by_hour": by_hour, "by_day": dict(sorted(by_day.items()))}


def genre_stats(played: list[Played], genres_by_game: dict[str, list[str]]) -> list[dict]:
    """The genres with the most time, most first. A game of several genres counts its time in each of them
    (as the affinity does); a game without genres counts in none."""
    totals: dict[str, int] = {}
    for session in played:
        for genre in genres_by_game.get(session.game_id, []):
            totals[genre] = totals.get(genre, 0) + session.seconds
    top = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:TOP_GENRES]
    return [{"genre": genre, "seconds": seconds} for genre, seconds in top]


def top_games(played: list[Played], games: dict[str, dict], limit: int = TOP_PLAYER_GAMES) -> list[dict]:
    """The games with the most time, most first, with their cover and name; the smallest id wins a tie."""
    totals = _sum_by(played, lambda s: s.game_id)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{**games.get(game_id, {"id": game_id, "name": game_id, "image_url": None}), "seconds": seconds} for game_id, seconds in ranked]


def playmates(played: list[Played]) -> dict[int, tuple[int, int]]:
    """For each player, (who, seconds) of the one they spent the most time with in the same game at the same time.

    Only sessions that overlap in time on the same game count; the smallest id wins a tie."""
    by_game: dict[str, list[Played]] = {}
    for session in played:
        if session.end is not None:
            by_game.setdefault(session.game_id, []).append(session)
    together: dict[tuple[int, int], int] = {}
    for sessions in by_game.values():
        sessions.sort(key=lambda s: s.start)
        for i, first in enumerate(sessions):
            for second in sessions[i + 1 :]:
                if second.start >= first.end:
                    break  # sorted by start: nobody later overlaps `first` either
                if first.user_id == second.user_id:
                    continue
                pair = tuple(sorted((first.user_id, second.user_id)))
                overlap = (min(first.end, second.end) - second.start).total_seconds()
                together[pair] = together.get(pair, 0) + int(overlap)
    mates: dict[int, dict[int, int]] = {}
    for (a, b), seconds in together.items():
        mates.setdefault(a, {})[b] = seconds
        mates.setdefault(b, {})[a] = seconds
    return {user_id: _top(others) for user_id, others in mates.items()}


def group_stats(played: list[Played]) -> dict:
    """What the group did in the period."""
    busiest = _top(_sum_by(played, lambda s: s.start.date()))
    games: dict[str, dict] = {}
    for session in played:
        game = games.setdefault(session.game_id, {"game_id": session.game_id, "seconds": 0, "players": set()})
        game["seconds"] += session.seconds
        game["players"].add(session.user_id)
    top_games = sorted(games.values(), key=lambda g: (-g["seconds"], g["game_id"]))[:TOP_GAMES]
    return {
        "seconds": sum(s.seconds for s in played),
        "sessions": len(played),
        "players": len({s.user_id for s in played}),
        "busiest_day": busiest[0] if busiest else None,
        "busiest_day_seconds": busiest[1] if busiest else 0,
        "top_games": [{**g, "players": len(g["players"])} for g in top_games],
    }


def _period_sessions(db: Session, period: Period, *columns):
    """The finished sessions that started in the period, of every player (never the emergency account's)."""
    sessions = time_entries.sessions_subquery()
    return (
        db.query(*(getattr(sessions.c, name) for name in columns))
        .join(models.User, models.User.id == sessions.c.user_id)
        .filter(models.not_god(), sessions.c.duration > 0)
        .filter(sessions.c.start >= datetime.datetime.combine(period.start, datetime.time.min))
        .filter(sessions.c.start < datetime.datetime.combine(period.end, datetime.time.min))
    )


def _played(db: Session, period: Period) -> list[Played]:
    """The finished sessions that started in the period, of every player."""
    rows = _period_sessions(db, period, "user_id", "game_id", "start", "end", "duration")
    return [Played(user_id, game_id, start, end, int(seconds)) for user_id, game_id, start, end, seconds in rows]


def anyone_played(db: Session, period: Period) -> bool:
    """Did anybody play in the period? (what decides whether there is anything to announce)"""
    return _period_sessions(db, period, "user_id").first() is not None


def _count_by_user(query) -> dict[int, int]:
    return {user_id: int(total) for user_id, total in query.group_by(models.UserGame.user_id)}


def _library(db: Session, period: Period) -> tuple[dict[int, int], dict[int, int]]:
    """Games started and games completed in the period, per player."""
    started = _count_by_user(
        db.query(models.UserGame.user_id, func.count())
        .filter(models.UserGame.started_date >= period.start, models.UserGame.started_date < period.end)
    )
    completed = _count_by_user(
        db.query(models.UserGame.user_id, func.count())
        .filter(models.UserGame.completed == 1)
        .filter(models.UserGame.completed_date >= period.start, models.UserGame.completed_date < period.end)
    )
    return started, completed


def _achievements(db: Session, period: Period) -> list[dict]:
    """What was earned in the period, with how many players hold each achievement (ever), oldest first."""
    holders = (
        db.query(models.UserAchievement.achievement_id, func.count(func.distinct(models.UserAchievement.user_id)).label("holders"))
        .group_by(models.UserAchievement.achievement_id)
        .subquery()
    )
    rows = (
        db.query(
            models.UserAchievement.user_id,
            models.UserAchievement.date,
            models.Achievement.id,
            models.Achievement.title,
            models.Achievement.secret,
            holders.c.holders,
        )
        .join(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
        .join(holders, holders.c.achievement_id == models.Achievement.id)
        .join(models.User, models.User.id == models.UserAchievement.user_id)
        .filter(models.not_god(), models.Achievement.active == True)  # noqa: E712
        .filter(models.UserAchievement.date >= period.start, models.UserAchievement.date < period.end)
        .order_by(models.UserAchievement.date, models.Achievement.id)
    )
    return [
        {"user_id": user_id, "date": date, "id": achievement_id, "title": title, "secret": bool(secret), "holders": int(count)}
        for user_id, date, achievement_id, title, secret, count in rows
    ]


def rarest(earned: list[dict]) -> dict | None:
    """The earned achievement held by the fewest players; the first one earned wins a tie."""
    if not earned:
        return None
    best = min(earned, key=lambda a: (a["holders"], a["date"], a["id"]))
    return {"title": best["title"], "holders": best["holders"], "date": best["date"]}


def _seconds_by_user(db: Session, period: Period) -> dict[int, int]:
    return _sum_by(_played(db, period), lambda s: s.user_id)


def build_recap(db: Session, period: Period, user_id: int | None = None, today: datetime.date | None = None) -> dict:
    """The recap of the group in the period and, with `user_id`, the one of that player.

    The group part leaves out the secret achievements (the player's own recap keeps theirs: they already know)."""
    today = today or datetime.date.today()
    played = _played(db, period)
    seconds = _sum_by(played, lambda s: s.user_id)
    previous = _seconds_by_user(db, period.previous())
    people = list(db.query(models.User).filter(models.not_god()))
    names = {user.id: user.name for user in people}
    active = {user.id: bool(user.is_active) for user in people}
    started, completed = _library(db, period)
    earned = _achievements(db, period)
    mates = playmates(played)

    ranking = sorted(seconds, key=lambda uid: (-seconds[uid], uid))
    game_ids = {s.game_id for s in played}
    games, genres_by_game = {}, {}
    for game in db.query(models.Game).filter(models.Game.id.in_(game_ids)) if game_ids else []:
        games[game.id] = {"id": game.id, "name": game.name, "image_url": game.image_url}
        genres_by_game[game.id] = games_crud.genre_list(game.genres)

    group = group_stats(played)
    group["top_games"] = [{**g, **games.get(g["game_id"], {})} for g in group["top_games"]]
    group["ranking"] = [
        {"user_id": uid, "name": names.get(uid), "active": active.get(uid, False), "seconds": seconds[uid], "previous_seconds": previous.get(uid, 0)}
        for uid in ranking
    ]
    group.update(activity_stats(played), genres=genre_stats(played, genres_by_game))
    group["previous_seconds"] = sum(previous.values())
    group["achievements"] = sum(1 for a in earned if not a["secret"])
    group["rarest_achievement"] = rarest([a for a in earned if not a["secret"]])

    player = None
    if user_id is not None:
        mine = [s for s in played if s.user_id == user_id]
        player = player_stats(mine, period)
        star = games.get(player["star_game_id"])
        mate = mates.get(user_id)
        own_achievements = [a for a in earned if a["user_id"] == user_id]
        player.update(
            activity_stats(mine),
            genres=genre_stats(mine, genres_by_game),
            top_games=top_games(mine, games),
            user_id=user_id,
            name=names.get(user_id),
            previous_seconds=previous.get(user_id, 0),
            position=ranking.index(user_id) + 1 if user_id in seconds else None,
            star_game=star and {**star, "seconds": player["star_game_seconds"]},
            games_started=started.get(user_id, 0),
            games_completed=completed.get(user_id, 0),
            achievements=len(own_achievements),
            rarest_achievement=rarest(own_achievements),
            playmate=mate and {"user_id": mate[0], "name": names.get(mate[0]), "seconds": mate[1]},
        )
        del player["star_game_id"], player["star_game_seconds"]

    return {
        "period": period.key,
        "kind": period.kind,
        "start": period.start,
        "end": period.last_day,
        "complete": today >= period.end,
        "group": group,
        "player": player,
    }

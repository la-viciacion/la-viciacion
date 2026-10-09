import datetime
from typing import Union

from sqlalchemy import (
    Integer,
    asc,
    cast,
    create_engine,
    desc,
    extract,
    func,
    select,
    text,
    true,
    update,
)
from sqlalchemy.orm import Session

from ..config import Config
from ..database import models, schemas
from ..utils import actions
from ..utils import my_utils as utils
from . import games, users
from ..utils.logger import LogManager
from ..utils import seasons, user_settings

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


def _in_season(column, season: int):
    """`column` is in the season (any season when asked for seasons.ALL)."""
    return true() if season == seasons.ALL else column == season


def sessions_subquery():
    """Normalized "played session" rows.

    Finished (is_active == False) GameTimer rows only. Every aggregate query
    below sees a single (user_id, game_id, start, end, duration) shape.
    """
    return (
        select(
            models.GameTimer.user_id.label("user_id"),
            models.GameTimer.game_id.label("game_id"),
            models.GameTimer.season.label("season"),
            models.GameTimer.start_time.label("start"),
            models.GameTimer.end_time.label("end"),
            models.GameTimer.duration_seconds.label("duration"),
        )
        .where(models.GameTimer.is_active == False)
        .subquery("sessions")
    )


def players_played_time(db: Session, season: int = None, is_active: bool | None = None) -> list[dict]:
    """Every player with the seconds played in the season (0 if none), most first."""
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    total = (
        select(sessions.c.user_id, func.sum(sessions.c.duration).label("seconds"))
        .where(sessions.c.season == season)
        .group_by(sessions.c.user_id)
        .subquery()
    )
    played = cast(func.coalesce(total.c.seconds, 0), Integer).label("played_time")
    stmt = (
        select(models.User.id.label("user_id"), models.User.name, played)
        .outerjoin(total, total.c.user_id == models.User.id)
        .where(models.not_god())
    )
    if is_active is not None:
        stmt = stmt.where(models.User.is_active == is_active)
    rows = db.execute(stmt.order_by(desc(played), models.User.id)).all()
    return [dict(row._mapping) for row in rows]


# A session shorter than this does not count for the achievements that count things (days, streaks,
# games in a day): it keeps someone who just opens a game for a few seconds from earning them. Hours add
# up whatever the length of each session, "Lo he abierto sin querer" is judged when a timer stops and the
# ones that fire when a timer starts (early riser, nocturnal, new year) cannot know it.
MIN_SESSION_SECONDS = 600


def played_days_by_user(
    db: Session, season: int, user_ids: list[int] | None = None, since: int | None = None
) -> dict[int, list[datetime.date]]:
    """{user_id: sorted days on which they played in the season}, only for users that played. Over every
    season (seasons.ALL), `since` leaves out the days before that season.

    A day is played when a finished session of 10 minutes or more touched it: the day it began and
    the day it ended, so one that crosses midnight counts for both. Each day belongs to the season of
    its own year, whatever the season of the session (that is the one it began in): playing from
    31 December into 1 January gives a day to each year."""
    sessions = sessions_subquery()
    stmt = select(sessions.c.user_id, sessions.c.start, sessions.c.end).where(
        sessions.c.duration >= MIN_SESSION_SECONDS
    )
    if season != seasons.ALL:
        stmt = stmt.where(
            sessions.c.start < datetime.datetime(season + 1, 1, 1),
            sessions.c.end >= datetime.datetime(season, 1, 1),
        )
    elif since:
        stmt = stmt.where(sessions.c.end >= datetime.datetime(since, 1, 1))
    if user_ids is not None:
        stmt = stmt.where(sessions.c.user_id.in_(user_ids))
    days: dict[int, set] = {}
    for user_id, start, end in db.execute(stmt).all():
        for moment in (start, end):
            if moment is not None and (moment.year >= (since or 0) if season == seasons.ALL else moment.year == season):
                days.setdefault(user_id, set()).add(moment.date())
    return {user_id: sorted(values) for user_id, values in days.items()}


def players_played_dates(db: Session, season: int = None, is_active: bool | None = None) -> dict:
    """{user_id: sorted list of the days played in the season} (see played_days_by_user).

    Every player is a key, with an empty list when they have not played."""
    season = seasons.or_current(season)
    players = select(models.User.id).where(models.not_god())
    if is_active is not None:
        players = players.where(models.User.is_active == is_active)
    played = played_days_by_user(db, season)
    return {user_id: played.get(user_id, []) for (user_id,) in db.execute(players).all()}


def games_played_time(db: Session, season: int = None, limit: int | None = None, is_active: bool | None = None) -> list[dict]:
    """Games with the seconds played in the season, most first (only games that were played)."""
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    played = cast(func.sum(sessions.c.duration), Integer).label("played_time")
    stmt = (
        select(sessions.c.game_id.label("game_id"), models.Game.name, played)
        .join(models.User, sessions.c.user_id == models.User.id)
        .join(models.Game, models.Game.id == sessions.c.game_id)
        .where(sessions.c.season == season, models.not_god())
        .group_by(sessions.c.game_id, models.Game.name)
        .having(func.sum(sessions.c.duration) > 0)
        .order_by(desc(played), models.Game.name)
    )
    if is_active is not None:
        stmt = stmt.where(models.User.is_active == is_active)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [dict(row._mapping) for row in db.execute(stmt).all()]


def entry_played_time(user_id: int | None = None):
    """Seconds played per (user, game, season): the time of a library entry.

    With `user_id` only that user's sessions are summed: the caller filters by that user
    anyway, and saying it here keeps the database from summing everybody's first."""
    sessions = sessions_subquery()
    stmt = select(
        sessions.c.user_id.label("user_id"),
        sessions.c.game_id.label("game_id"),
        sessions.c.season.label("season"),
        cast(func.sum(sessions.c.duration), Integer).label("played_time"),
    )
    if user_id is not None:
        stmt = stmt.where(sessions.c.user_id == user_id)
    return stmt.group_by(sessions.c.user_id, sessions.c.game_id, sessions.c.season).subquery("entry_time")


def get_user_played_time(db: Session, user_id: str, season: int = None):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    stmt = (
        select(
            sessions.c.user_id,
            func.sum(sessions.c.duration),
        )
        .where(
            sessions.c.user_id == user_id,
            _in_season(sessions.c.season, season),
        )
        .group_by(sessions.c.user_id)
    )
    return db.execute(stmt).first()


def get_first_time_entry_on_day(db: Session, user_id: int, day: datetime.date):
    """The earliest finished session that was running at some point of `day`, or None.

    It includes the one that started the day before and ended on `day` (or later), which belongs to
    the previous season by its start: that is why the caller needs the row and not only a yes/no.

    Returns:
        Row | None: row with (user_id, game_id, season, start, end, duration)
    """
    day_start = datetime.datetime.combine(day, datetime.time.min)
    sessions = sessions_subquery()
    return db.execute(
        select(sessions)
        .where(
            sessions.c.user_id == user_id,
            sessions.c.start < day_start + datetime.timedelta(days=1),
            sessions.c.end >= day_start,
        )
        .order_by(sessions.c.start)
    ).first()


def get_user_games_played_time(
    db: Session, user_id: str, game_id: str = None, season: int = None
):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    query = db.query(
        sessions.c.game_id,
        func.sum(sessions.c.duration),
    ).filter(
        sessions.c.user_id == user_id,
        sessions.c.season == season,
    )
    if game_id is not None:
        query = query.filter(sessions.c.game_id == game_id)
    return query.group_by(sessions.c.game_id).all()


def get_played_days(db: Session, user_id: int, season: int = None, since: int | None = None) -> list[datetime.date]:
    """The days the user played in the season (see played_days_by_user), oldest first."""
    season = seasons.or_current(season)
    return played_days_by_user(db, season, [user_id], since).get(user_id, [])


def get_time_entry_by_time(
    db: Session,
    user_id: int,
    duration: int,
    mode: int,
    season: int = None,
):
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        duration (int): _description_
        mode (int): 1==, 2<=, 3>=

    Returns:
        Row | None: row with (user_id, game_id, start, end, duration)
    """
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    # sessions of no duration never count; the earliest one that matches is the one that earned it
    query = db.query(sessions).filter(
        sessions.c.user_id == user_id,
        sessions.c.season == season,
        sessions.c.duration > 0,
    ).order_by(sessions.c.start)
    if mode == 1:
        time_entry = query.filter(sessions.c.duration == duration).first()
    elif mode == 2:
        time_entry = query.filter(sessions.c.duration <= duration).first()
    elif mode == 3:
        time_entry = query.filter(sessions.c.duration >= duration).first()
    else:
        time_entry = None
    return time_entry


def get_played_time_by_day(db: Session, user_id: int, season: int = None, since: int | None = None):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    played_start_days = (
        db.query(func.DATE(sessions.c.start), func.sum(sessions.c.duration))
        .filter(
            sessions.c.user_id == user_id,
            _in_season(sessions.c.season, season),
            sessions.c.season >= (since or 0),
        )
        .group_by(func.DATE(sessions.c.start))
        .all()
    )
    return sorted(played_start_days)


def get_played_time_by_game_and_day(db: Session, user_id: int, season: int = None, since: int | None = None):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    return (
        db.query(
            func.DATE(sessions.c.start),
            sessions.c.game_id,
            func.sum(sessions.c.duration),
        )
        .filter(
            sessions.c.user_id == user_id,
            _in_season(sessions.c.season, season),
            sessions.c.season >= (since or 0),
        )
        .group_by(func.DATE(sessions.c.start), sessions.c.game_id)
        .all()
    )


def get_played_games_count_by_day(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    return (
        db.query(
            func.DATE(sessions.c.start),
            func.count(func.distinct(sessions.c.game_id)),
        )
        .filter(
            sessions.c.user_id == user_id,
            sessions.c.season == season,
            sessions.c.duration >= MIN_SESSION_SECONDS,
        )
        .group_by(func.DATE(sessions.c.start))
        .all()
    )


def get_first_time_entry_between_hours(
    db: Session,
    user_id: int,
    start_hour: int,
    end_hour: int,
    season: int = None,
):
    """The earliest session of the season that began between two hours of the day, or None.

    Args:
        start_hour (int): Include this hour
        end_hour (int): Exclude this hour (search until 1 minute before)

    Returns:
        Row | None: row with (user_id, game_id, season, start, end, duration)
    """
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    return (
        db.query(sessions)
        .filter(sessions.c.user_id == user_id)
        .filter(extract("hour", sessions.c.start) >= start_hour)
        .filter(extract("hour", sessions.c.start) < end_hour)
        .filter(sessions.c.season == season)
        .order_by(sessions.c.start)
        .first()
    )


def active_timer_user_ids_of_game(db: Session, game_id: str) -> set[int]:
    """Ids of the users that have a timer running on the game right now."""
    rows = (
        db.query(models.GameTimer.user_id)
        .filter(models.GameTimer.is_active == True, models.GameTimer.game_id == game_id)  # noqa: E712
        .distinct()
        .all()
    )
    return {user_id for (user_id,) in rows}


def get_first_time_entry_across(db: Session, user_id: int, moment: datetime.datetime):
    """The earliest finished session that was running at `moment` (it began before and ended after), or None.

    Returns:
        Row | None: row with (user_id, game_id, season, start, end, duration)
    """
    sessions = sessions_subquery()
    return (
        db.query(sessions)
        .filter(sessions.c.user_id == user_id, sessions.c.start < moment, sessions.c.end > moment)
        .order_by(sessions.c.start)
        .first()
    )


def get_game_session_days(db: Session, user_id: int, game_id: str, season: int = None) -> list:
    """The distinct days the user's sessions of a game began on, in the season."""
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    return [
        day
        for (day,) in db.query(func.DATE(sessions.c.start))
        .filter(sessions.c.user_id == user_id, sessions.c.game_id == game_id, sessions.c.season == season)
        .distinct()
        .all()
    ]


def get_game_sessions(db: Session, user_id: int, game_id: str, until: datetime.date) -> list:
    """The user's finished sessions of a game, of any season, that began on `until` or before, oldest first, as
    (start, end, seconds) rows. What tells how long a game was left alone before being finished."""
    sessions = sessions_subquery()
    return (
        db.query(sessions.c.start, sessions.c.end, sessions.c.duration)
        .filter(
            sessions.c.user_id == user_id,
            sessions.c.game_id == game_id,
            sessions.c.start < datetime.datetime.combine(until + datetime.timedelta(days=1), datetime.time.min),
        )
        .order_by(sessions.c.start)
        .all()
    )


def get_sessions_since(db: Session, user_id: int, since: int | None = None) -> list:
    """The user's finished sessions, of any length, that began in season `since` or later, oldest first, as
    (game_id, start) rows. What the achievements about the outside world look through: they are about the moment a
    session started, like the timer that has just started is."""
    sessions = sessions_subquery()
    return (
        db.query(sessions.c.game_id, sessions.c.start)
        .filter(sessions.c.user_id == user_id, sessions.c.season >= (since or 0))
        .order_by(sessions.c.start)
        .all()
    )


def get_first_time_entry_on_release_day(db: Session, user_id: int, season: int = None):
    """The earliest session of the season that began on the day its game came out, or None.

    Returns:
        Row | None: row with (user_id, game_id, season, start, end, duration)
    """
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    return (
        db.query(sessions)
        .join(models.Game, models.Game.id == sessions.c.game_id)
        .filter(
            sessions.c.user_id == user_id,
            sessions.c.season == season,
            func.DATE(sessions.c.start) == models.Game.release_date,
        )
        .order_by(sessions.c.start)
        .first()
    )


def active_timer_user_ids(db: Session) -> set[int]:
    """Ids of the users that have a timer running right now: one query for everybody."""
    rows = db.query(models.GameTimer.user_id).filter(models.GameTimer.is_active == True).distinct().all()  # noqa: E712
    return {user_id for (user_id,) in rows}


def get_active_game_timer_by_user(db: Session, user_id: int) -> models.GameTimer:
    return (
        db.query(models.GameTimer)
        .filter(
            models.GameTimer.user_id == user_id,
            models.GameTimer.is_active == True,
        )
        .first()
    )


# A timer running for longer than this is more likely forgotten than played: shown dimmed
NOW_PLAYING_STALE_HOURS = 6


def get_now_playing(db: Session, viewer_id: int, now: datetime.datetime | None = None) -> list[dict]:
    """Who is playing right now: the running timers of the active players (never the emergency account),
    leaving out those who chose to hide it, except from themselves. The ones that are not stale come
    first, the latest started first. `stale`: running for more than NOW_PLAYING_STALE_HOURS."""
    now = now or datetime.datetime.now()
    rows = (
        db.query(models.GameTimer, models.User, models.Game, models.UserSettings.show_playing)
        .join(models.User, models.GameTimer.user_id == models.User.id)
        .outerjoin(models.Game, models.GameTimer.game_id == models.Game.id)
        .outerjoin(models.UserSettings, models.UserSettings.user_id == models.User.id)
        .filter(models.GameTimer.is_active == True, models.User.is_active == 1, models.not_god())  # noqa: E712
        .all()
    )
    limit = datetime.timedelta(hours=NOW_PLAYING_STALE_HOURS)
    playing = [
        {
            "user_id": user.id,
            "username": user.username,
            "name": user.name or user.username,
            "game_id": timer.game_id,
            "game_name": game.name if game else timer.game_id,
            "image_url": game.image_url if game else None,
            "platform": timer.platform,
            "start_time": timer.start_time,
            "stale": now - timer.start_time > limit,
        }
        for timer, user, game, show in rows
        if show is None or show or user.id == viewer_id
    ]
    return sorted(playing, key=lambda p: (p["stale"], -p["start_time"].timestamp()))


def get_running_game_timers(db: Session) -> list[models.GameTimer]:
    """Every running timer."""
    return db.query(models.GameTimer).filter(models.GameTimer.is_active == True).all()  # noqa: E712


def get_forgotten_game_timers(
    db: Session,
    user_id: int = None,
    hours: int = user_settings.DEFAULT_FORGOTTEN_TIMER_HOURS,
    newly_forgotten: bool = False,
) -> list[models.GameTimer]:
    """Running timers older than `hours`. With `newly_forgotten`, only those that crossed the
    line during the last hour, so an hourly job reminds about each timer once."""
    time_threshold = datetime.datetime.now() - datetime.timedelta(hours=hours)
    query = db.query(models.GameTimer).filter(
        models.GameTimer.is_active == True,
        models.GameTimer.start_time < time_threshold,
    )
    if newly_forgotten:
        query = query.filter(models.GameTimer.start_time >= time_threshold - datetime.timedelta(hours=1))
    if user_id is not None:
        query = query.filter(models.GameTimer.user_id == user_id)
    return query.all()


def get_weekly_resume(db: Session, user: models.User, weeks_ago: int = 0):
    """_summary_

    Args:
        db (Session): _description_
        user (models.User): _description_
        mode (int, optional): 0 = last week. 1 = current week. Defaults to 0.

    Returns:
        list[Row]: rows with (sum(duration), session count, distinct game count)
    """
    first_day, last_day = utils.get_week_range_dates(weeks_ago)
    sessions = sessions_subquery()
    weekly_hours = (
        db.query(
            func.sum(sessions.c.duration),
            func.count(),
            func.count(func.distinct(sessions.c.game_id)),
        )
        .filter(sessions.c.user_id == user.id)
        .filter(func.DATE(sessions.c.start) >= first_day)
        .filter(func.DATE(sessions.c.start) <= last_day)
        .filter(sessions.c.duration > 0)
        .all()
    )
    return weekly_hours

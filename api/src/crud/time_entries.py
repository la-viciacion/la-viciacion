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
    or_,
    select,
    text,
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


def players_played_time(db: Session, season: int = None, is_active: bool | None = True) -> list[dict]:
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
    stmt = select(models.User.id.label("user_id"), models.User.name, played).outerjoin(
        total, total.c.user_id == models.User.id
    )
    if is_active is not None:
        stmt = stmt.where(models.User.is_active == is_active)
    rows = db.execute(stmt.order_by(desc(played), models.User.id)).all()
    return [dict(row._mapping) for row in rows]


def players_played_dates(db: Session, season: int = None, is_active: bool | None = True) -> dict:
    """{user_id: sorted list of the days played in the season} (sessions of 10 minutes or more).

    Every player is a key, with an empty list when they have not played."""
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    players = select(models.User.id)
    if is_active is not None:
        players = players.where(models.User.is_active == is_active)
    days = {user_id: [] for (user_id,) in db.execute(players).all()}
    stmt = (
        select(sessions.c.user_id, func.DATE(sessions.c.start))
        .where(sessions.c.season == season, sessions.c.duration >= 600)
        .distinct()
    )
    for user_id, day in db.execute(stmt).all():
        if user_id in days:
            days[user_id].append(day)
    return {user_id: sorted(values) for user_id, values in days.items()}


def games_played_time(db: Session, season: int = None, limit: int | None = None, is_active: bool | None = True) -> list[dict]:
    """Games with the seconds played in the season, most first (only games that were played)."""
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    played = cast(func.sum(sessions.c.duration), Integer).label("played_time")
    stmt = (
        select(sessions.c.game_id.label("game_id"), models.Game.name, played)
        .join(models.User, sessions.c.user_id == models.User.id)
        .join(models.Game, models.Game.id == sessions.c.game_id)
        .where(sessions.c.season == season)
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
            sessions.c.season == season,
        )
        .group_by(sessions.c.user_id)
    )
    return db.execute(stmt).first()


def get_time_entry_by_date(db: Session, user_id: int, date: str, mode: int):
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        date (str): _description_
        mode (int): 1==, 2<=, 3>=

    Returns:
        list[Row]: rows with (user_id, game_id, start, end, duration)
    """
    sessions = sessions_subquery()
    base = select(sessions).where(sessions.c.user_id == user_id)
    if mode == 1:
        stmt = base.where(
            or_(
                func.DATE(sessions.c.start) == date,
                func.DATE(sessions.c.end) == date,
            ),
        )
    elif mode == 2:
        stmt = base.where(
            or_(
                func.DATE(sessions.c.start) <= date,
                func.DATE(sessions.c.end) <= date,
            ),
        )
    elif mode == 3:
        stmt = base.where(
            or_(
                func.DATE(sessions.c.start) >= date,
                func.DATE(sessions.c.end) >= date,
            ),
        )
    else:
        return []
    return db.execute(stmt).all()


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


def get_played_days(
    db: Session,
    user_id: int,
    start_date: str = None,
    end_date: str = None,
    season: int = None,
) -> tuple[list[datetime.date], list[datetime.date]]:
    season = seasons.or_current(season)
    played_days = []
    real_played_days = []
    if start_date is None:
        current_date = datetime.datetime.now()
        start_date = str(current_date.year) + "-01-01"
    if end_date is None:
        end_date = "3000-12-31"
    sessions = sessions_subquery()
    played_start_days = (
        db.query(func.DATE(sessions.c.start))
        .filter(sessions.c.user_id == user_id)
        .filter(func.DATE(sessions.c.start) >= start_date)
        .filter(func.DATE(sessions.c.start) <= end_date)
        .filter(sessions.c.season == season)
        .filter(sessions.c.duration >= 600)
        .distinct()
        .all()
    )
    played_end_days = (
        db.query(func.DATE(sessions.c.end))
        .filter(sessions.c.user_id == user_id)
        .filter(func.DATE(sessions.c.end) >= start_date)
        .filter(func.DATE(sessions.c.end) <= end_date)
        .filter(sessions.c.season == season)
        .filter(sessions.c.duration >= 600)
        .distinct()
        .all()
    )
    for played_day in played_start_days:
        played_days.append(played_day[0])
        real_played_days.append(played_day[0])
    for played_day in played_end_days:
        played_days.append(played_day[0])
    played_days = list(set(played_days))  # Remove duplicates
    real_played_days = sorted(real_played_days)
    played_days = sorted(played_days)
    return played_days, real_played_days


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


def get_played_time_by_day(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    played_start_days = (
        db.query(func.DATE(sessions.c.start), func.sum(sessions.c.duration))
        .filter(
            sessions.c.user_id == user_id,
            sessions.c.season == season,
        )
        .group_by(func.DATE(sessions.c.start))
        .all()
    )
    return sorted(played_start_days)


def get_played_time_by_game_and_day(db: Session, user_id: int, season: int = None):
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
            sessions.c.season == season,
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
        )
        .group_by(func.DATE(sessions.c.start))
        .all()
    )


def get_time_entry_between_hours(
    db: Session,
    user_id: int,
    start_hour: int,
    end_hour: int,
    season: int = None,
):
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        start_hour (int): Include this hour
        end_hour (int): Exclude this hour (search until 1 minute before)

    Returns:
        list[Row]: rows with (user_id, game_id, start, end, duration)
    """
    season = seasons.or_current(season)
    sessions = sessions_subquery()
    entries = (
        db.query(sessions)
        .filter(sessions.c.user_id == user_id)
        .filter(extract("hour", sessions.c.start) >= start_hour)
        .filter(extract("hour", sessions.c.start) < end_hour)
        .filter(sessions.c.season == season)
        .all()
    )
    return entries


def get_active_game_timer_by_user(db: Session, user_id: int) -> models.GameTimer:
    return (
        db.query(models.GameTimer)
        .filter(
            models.GameTimer.user_id == user_id,
            models.GameTimer.is_active == True,
        )
        .first()
    )


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

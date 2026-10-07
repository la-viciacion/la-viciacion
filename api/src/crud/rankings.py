import datetime
from typing import Union

from sqlalchemy import and_, asc, case, create_engine, desc, func, select, text, update
from sqlalchemy.orm import Session

from ..crud import time_entries, users
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.logger import LogManager
from ..utils import seasons, streaks
from ..config import Config

log_manager = LogManager()
logger = log_manager.get_logger()
config = Config()

####################
##### RANKINGS #####
####################


def user_hours_players(db: Session, limit: int = None, is_active: bool | None = None) -> list[dict]:
    rows = time_entries.players_played_time(db, is_active=is_active)
    return rows[:limit] if limit else rows


def players_with_dates(db: Session, is_active: bool | None = None):
    """(user_id, name, played days) of every player, for the rankings derived from the days played.

    Three rankings need it (days, best and current streak): a caller that asks for several
    computes it once and passes it as `players`."""
    names = {row["user_id"]: row["name"] for row in time_entries.players_played_time(db, is_active=is_active)}
    return [(user_id, names[user_id], days) for user_id, days in time_entries.players_played_dates(db, is_active=is_active).items()]


def user_days_played(db: Session, limit: int = None, is_active: bool | None = None, players=None) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "played_days": len(days)}
        for user_id, name, days in (players if players is not None else players_with_dates(db, is_active))
    ]
    rows.sort(key=lambda r: (-r["played_days"], r["user_id"]))
    return rows[:limit] if limit else rows


def _streaks(db: Session, is_active: bool | None, players=None):
    today = datetime.date.today()
    season = seasons.current()
    for user_id, name, days in (players if players is not None else players_with_dates(db, is_active)):
        yield user_id, name, streaks.streak_summary(days, today, season)


def user_best_streak(db: Session, limit: int = None, is_active: bool | None = None, players=None) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "best_streak": summary[1], "best_streak_date": summary[0]}
        for user_id, name, summary in _streaks(db, is_active, players)
    ]
    rows.sort(key=lambda r: (-r["best_streak"], r["user_id"]))
    return rows[:limit] if limit else rows


def user_current_streak(db: Session, limit: int = None, is_active: bool | None = None, players=None) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "current_streak": summary[2]}
        for user_id, name, summary in _streaks(db, is_active, players)
    ]
    rows.sort(key=lambda r: (-r["current_streak"], r["user_id"]))
    return rows[:limit] if limit else rows


def user_ranking_achievements(
    db: Session,
    limit: int = None,
    season: int = None,
    is_active: bool | None = None,
):
    season = seasons.or_current(season)
    try:
        stmt = (
            select(
                models.UserAchievement.user_id,
                func.count(models.UserAchievement.achievement_id).label("achievements"),
                models.User.name,
            )
            .filter(models.UserAchievement.season == season, models.not_god())
            .join(models.User, models.User.id == models.UserAchievement.user_id)
            .group_by(models.UserAchievement.user_id, models.User.name)
            .order_by(func.count(models.UserAchievement.achievement_id).desc(), models.UserAchievement.user_id)
            .limit(limit)
        )
        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e


def user_played_games(
    db: Session,
    limit: int = None,
    season: int = None,
    is_active: bool | None = None,
):
    season = seasons.or_current(season)
    try:
        stmt = (
            select(
                models.UserGame.user_id,
                func.count(func.distinct(models.UserGame.game_id)).label("played_games"),
                models.User.name,
            )
            .filter(models.UserGame.season == season, models.not_god())
            .join(models.User, models.User.id == models.UserGame.user_id)
        )

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = (
            stmt.group_by(models.UserGame.user_id, models.User.name)
            .order_by(func.count(func.distinct(models.UserGame.game_id)).desc(), models.UserGame.user_id)
            .limit(limit)
        )

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user played games: " + str(e))
        raise e


def library_counts(db: Session, season: int = None, is_active: bool | None = None) -> list[dict]:
    """Per player: library entries of the season and how many are completed (one query).

    Every player is there, with zeros when they have no entries."""
    season = seasons.or_current(season)
    completed = func.coalesce(func.sum(case((models.UserGame.completed == 1, 1), else_=0)), 0)
    stmt = (
        select(models.User.id, models.User.name, func.count(models.UserGame.game_id), completed)
        .select_from(models.User)
        .outerjoin(
            models.UserGame,
            and_(models.UserGame.user_id == models.User.id, models.UserGame.season == season),
        )
        .where(models.not_god())
        .group_by(models.User.id, models.User.name)
    )
    if is_active is not None:
        stmt = stmt.where(models.User.is_active == is_active)
    return [
        {"user_id": user_id, "name": name, "entries": entries, "completed": int(done)}
        for user_id, name, entries, done in db.execute(stmt).all()
    ]


def user_completed_games(
    db: Session,
    limit: int = None,
    season: int = None,
    is_active: bool | None = None,
    counts=None,
):
    counts = counts if counts is not None else library_counts(db, season, is_active)
    data = [{"user_id": c["user_id"], "name": c["name"], "completed_games": c["completed"]} for c in counts]
    return sorted(data, key=lambda x: (-x["completed_games"], x["user_id"]))


def games_last_played(db: Session, limit: int = 10):
    """The games played most recently, each once, with the start of their latest session."""
    try:
        sessions = time_entries.sessions_subquery()
        last = func.max(sessions.c.start).label("start")
        # group and cut first (game ids only), then look the names up for the few that remain
        latest = (
            select(sessions.c.game_id, last)
            .join(models.User, models.User.id == sessions.c.user_id)
            .where(models.not_god())
            .group_by(sessions.c.game_id)
            .order_by(desc(last))
            .limit(limit)
            .subquery("latest")
        )
        stmt = (
            select(latest.c.game_id, models.Game.name, latest.c.start)
            .join(models.Game, models.Game.id == latest.c.game_id)
            .order_by(desc(latest.c.start))
        )
        # .mappings() so `item["name"]` string-key access works (SQLAlchemy
        # 2.x plain Row no longer supports it, only via _mapping/.mappings()).
        return db.execute(stmt).mappings().all()
    except Exception as e:
        logger.info(e)
        raise e


def games_most_played(db: Session, limit: int = 10) -> list[dict]:
    return time_entries.games_played_time(db, limit=limit)


def platform_played_games(db: Session, limit: int = None):
    try:
        stmt = (
            select(
                (models.UserGame.platform).label("tag_id"),
                models.PlatformTag.name,
                func.count(models.UserGame.platform),
            )
            .join(
                models.PlatformTag,
                models.UserGame.platform == models.PlatformTag.id,
            )
            .join(models.User, models.User.id == models.UserGame.user_id)
            .where(models.not_god())
            .group_by(models.UserGame.platform)
            .order_by(func.count(models.UserGame.platform).desc())
            .limit(limit)
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e


def user_ratio(db: Session, season: int = None, is_active: bool | None = None, counts=None):
    counts = counts if counts is not None else library_counts(db, season, is_active)
    data = [
        {
            "user_id": c["user_id"],
            "name": c["name"],
            "ratio": round(c["completed"] / c["entries"], 2) if c["entries"] and c["completed"] else 0,
        }
        for c in counts
    ]
    return sorted(data, key=lambda x: (-x["ratio"], x["user_id"]))

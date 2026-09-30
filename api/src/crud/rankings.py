import datetime
from typing import Union

from sqlalchemy import asc, create_engine, desc, func, select, text, update
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


def user_hours_players(db: Session, limit: int = None, is_active: bool | None = True) -> list[dict]:
    rows = time_entries.players_played_time(db, is_active=is_active)
    return rows[:limit] if limit else rows


def _players_with_dates(db: Session, is_active: bool | None):
    """(user row, played days) for every player, for the rankings derived from the days played."""
    names = {row["user_id"]: row["name"] for row in time_entries.players_played_time(db, is_active=is_active)}
    return [(user_id, names[user_id], days) for user_id, days in time_entries.players_played_dates(db, is_active=is_active).items()]


def user_days_played(db: Session, limit: int = None, is_active: bool | None = True) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "played_days": len(days)}
        for user_id, name, days in _players_with_dates(db, is_active)
    ]
    rows.sort(key=lambda r: (-r["played_days"], r["user_id"]))
    return rows[:limit] if limit else rows


def _streaks(db: Session, is_active: bool | None):
    today = datetime.date.today()
    season = seasons.current()
    for user_id, name, days in _players_with_dates(db, is_active):
        yield user_id, name, streaks.streak_summary(days, today, season)


def user_best_streak(db: Session, limit: int = None, is_active: bool | None = True) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "best_streak": summary[1], "best_streak_date": summary[0]}
        for user_id, name, summary in _streaks(db, is_active)
    ]
    rows.sort(key=lambda r: (-r["best_streak"], r["user_id"]))
    return rows[:limit] if limit else rows


def user_current_streak(db: Session, limit: int = None, is_active: bool | None = True) -> list[dict]:
    rows = [
        {"user_id": user_id, "name": name, "current_streak": summary[2]}
        for user_id, name, summary in _streaks(db, is_active)
    ]
    rows.sort(key=lambda r: (-r["current_streak"], r["user_id"]))
    return rows[:limit] if limit else rows


def user_ranking_achievements(
    db: Session,
    limit: int = None,
    season: int = None,
    is_active: bool | None = True,
):
    season = seasons.or_current(season)
    try:
        stmt = (
            select(
                models.UserAchievement.user_id,
                func.count(models.UserAchievement.achievement_id).label("achievements"),
                models.User.name,
            )
            .filter(models.UserAchievement.season == season)
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
    is_active: bool | None = True,
):
    season = seasons.or_current(season)
    try:
        stmt = (
            select(
                models.UserGame.user_id,
                func.count(func.distinct(models.UserGame.game_id)).label("played_games"),
                models.User.name,
            )
            .filter(models.UserGame.season == season)
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


def user_completed_games(
    db: Session,
    limit: int = None,
    season: int = None,
    is_active: bool | None = True,
):
    season = seasons.or_current(season)
    try:
        user_list = users.get_users(db, is_active=is_active)
        data = []
        for user in user_list:
            user_data = {}
            stmt = (
                select(
                    func.count(models.UserGame.game_id),
                )
                .filter(models.UserGame.user_id == user.id)
                .filter(models.UserGame.completed == 1)
                .filter(models.UserGame.season == season)
                .limit(limit)
            )
            completed = db.execute(stmt).fetchone()[0]
            user_data["user_id"] = user.id
            user_data["name"] = user.name
            user_data["completed_games"] = completed
            data.append(user_data)

        ordered_data = sorted(data, key=lambda x: (-x["completed_games"], x["user_id"]))
        return ordered_data
    except Exception as e:
        logger.error("Error getting user completed games: " + str(e))
        raise e


def games_last_played(db: Session, limit: int = 10):
    """The games played most recently, each once, with the start of their latest session."""
    try:
        sessions = time_entries.sessions_subquery()
        last = func.max(sessions.c.start).label("start")
        stmt = (
            select(sessions.c.game_id, models.Game.name, last)
            .join(models.Game, models.Game.id == sessions.c.game_id)
            .group_by(sessions.c.game_id, models.Game.name)
            .order_by(desc(last))
            .limit(limit)
        )
        # .mappings() so `item["name"]` string-key access works (SQLAlchemy
        # 2.x plain Row no longer supports it, only via _mapping/.mappings()).
        return db.execute(stmt).mappings().all()
    except Exception as e:
        logger.info(e)
        raise e


def user_last_played_games(
    db: Session, limit: int = None, is_active: bool | None = True
):
    try:
        sessions = time_entries.sessions_subquery()
        stmt = select(
            sessions.c.game_id,
            sessions.c.user_id,
            sessions.c.start,
            models.User.name,
        ).join(models.User, models.User.id == sessions.c.user_id)

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = stmt.order_by(desc(sessions.c.start)).limit(limit)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user last played games: " + str(e))
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
            .group_by(models.UserGame.platform)
            .order_by(func.count(models.UserGame.platform).desc())
            .limit(limit)
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e


def user_ratio(db: Session, season: int = None, is_active: bool | None = True):
    season = seasons.or_current(season)
    try:
        user_list = users.get_users(db, is_active=is_active)
        data = []
        for user in user_list:
            user_data = {}
            stmt = (
                select(
                    func.count(models.UserGame.game_id),
                )
                .filter(models.UserGame.user_id == user.id)
                .filter(models.UserGame.season == season)
            )
            played = db.execute(stmt).fetchone()[0]

            stmt = (
                select(
                    func.count(models.UserGame.game_id),
                )
                .filter(models.UserGame.user_id == user.id)
                .filter(models.UserGame.completed == 1)
                .filter(models.UserGame.season == season)
            )
            completed = db.execute(stmt).fetchone()[0]

            if played == 0 or completed == 0:
                ratio = 0
            else:
                ratio = round((completed / played), 2)

            user_data["user_id"] = user.id
            user_data["name"] = user.name
            user_data["ratio"] = ratio
            data.append(user_data)

        ordered_data = sorted(data, key=lambda x: (-x["ratio"], x["user_id"]))
        return ordered_data
    except Exception as e:
        logger.error("Error calculating user ratio: " + str(e))
        raise e

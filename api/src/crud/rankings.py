import datetime
from typing import Union

from sqlalchemy import asc, create_engine, desc, func, select, text, update
from sqlalchemy.orm import Session

from ..crud import users
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.clockify_api import ClockifyApi
from ..utils.logger import LogManager
from ..config import Config

log_manager = LogManager()
logger = log_manager.get_logger()
config = Config()
clockify = ClockifyApi()
current_season = datetime.datetime.now().year

####################
##### RANKINGS #####
####################


def user_hours_players(
    db: Session, limit: int = None, is_active: bool | None = True
) -> list[models.User]:
    try:
        stmt = select(
            models.User.id.label("user_id"),
            models.User.name,
            models.UserStatistics.played_time,
        ).join(models.UserStatistics, models.User.id == models.UserStatistics.user_id)
        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = stmt.order_by(desc(models.UserStatistics.played_time)).limit(limit)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error retrieving user hours players: " + str(e))
        raise


def user_current_ranking(db: Session, user: models.User, is_active: bool | None = True):
    """
    Get the current ranking hours for a specific user, optionally filtering by active status.

    Args:
        db (Session): DB Session
        user (models.User): The user to get the ranking for.
        is_active (bool | None, optional): Filter by active status.
                                           True for active, False for inactive, None for all.

    Returns:
        list: Current ranking hours for the user.
    """
    try:
        stmt = (
            select(
                models.UserStatistics.current_ranking_hours,
            )
            .filter(models.UserStatistics.user_id == user.id)
            .join(
                models.UserStatistics, models.User.id == models.UserStatistics.user_id
            )
        )

        # Apply is_active filter if provided
        if is_active is not None:
            stmt = stmt.join(models.User).where(models.User.is_active == is_active)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error retrieving user current ranking: " + str(e))
        raise


def user_days_played(
    db: Session, limit: int = None, is_active: bool | None = True
) -> list[models.User]:
    try:
        stmt = select(
            models.User.id.label("user_id"),
            models.User.name,
            models.UserStatistics.played_days,
        ).join(models.UserStatistics, models.User.id == models.UserStatistics.user_id)

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = stmt.order_by(desc(models.UserStatistics.played_days)).limit(limit)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user days player: " + str(e))
        raise e


def user_best_streak(db: Session, limit: int = None, is_active: bool | None = True):
    try:
        stmt = select(
            models.User.id.label("user_id"),
            models.User.name,
            models.UserStatistics.best_streak,
            models.UserStatistics.best_streak_date,
        ).join(models.UserStatistics, models.User.id == models.UserStatistics.user_id)

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = stmt.order_by(desc(models.UserStatistics.best_streak)).limit(limit)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user best streak: " + str(e))
        raise e


def user_current_streak(db: Session, limit: int = None, is_active: bool | None = True):
    try:
        stmt = select(
            models.User.id.label("user_id"),
            models.User.name,
            models.UserStatistics.current_streak,
        ).join(models.UserStatistics, models.User.id == models.UserStatistics.user_id)

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = stmt.order_by(desc(models.UserStatistics.current_streak)).limit(limit)

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user current streak: " + str(e))
        raise e


def user_ranking_achievements(
    db: Session,
    limit: int = None,
    season: int = current_season,
    is_active: bool | None = True,
):
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
            .order_by(func.count(models.UserAchievement.achievement_id).desc())
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
    season: int = current_season,
    is_active: bool | None = True,
):
    try:
        stmt = (
            select(
                models.UserGame.user_id,
                func.count(models.UserGame.game_id).label("played_games"),
                models.User.name,
            )
            .filter(models.UserGame.season == season)
            .join(models.User, models.User.id == models.UserGame.user_id)
        )

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = (
            stmt.group_by(models.UserGame.user_id, models.User.name)
            .order_by(func.count(models.UserGame.game_id).desc())
            .limit(limit)
        )

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user played games: " + str(e))
        raise e


def user_completed_games(
    db: Session,
    limit: int = None,
    season: int = current_season,
    is_active: bool | None = True,
):
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

        ordered_data = sorted(data, key=lambda x: x["completed_games"], reverse=True)
        return ordered_data
    except Exception as e:
        logger.error("Error getting user completed games: " + str(e))
        raise e


def games_last_played(db: Session, limit: int = 10):
    try:
        stmt = (
            select(
                models.TimeEntry.project_clockify_id,
                models.Game.name,
                models.TimeEntry.start,
            )
            .join(
                models.Game,
                models.Game.id == models.TimeEntry.project_clockify_id,
            )
            .order_by(desc(models.TimeEntry.start))
        )
        result = db.execute(stmt).fetchall()
        unique_names = set()
        unique_data = []
        for item in result:
            if item["name"] not in unique_names:
                unique_names.add(item["name"])
                unique_data.append(item)
            if len(unique_data) == limit:
                break
        return unique_data
    except Exception as e:
        logger.info(e)
        raise e


def user_last_played_games(
    db: Session, limit: int = None, is_active: bool | None = True
):
    try:
        stmt = select(
            models.TimeEntry.project_clockify_id,
            models.TimeEntry.user_id,
            models.TimeEntry.start,
            models.User.name,
        ).join(models.User, models.User.id == models.TimeEntry.user_id)

        if is_active is not None:
            stmt = stmt.where(models.User.is_active == is_active)

        stmt = (
            stmt.filter(models.User.username == 1)
            .order_by(func.count(models.UserGame.game_id).desc())
            .limit(limit)
        )

        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error("Error getting user last played games: " + str(e))
        raise e


def games_most_played(db: Session, limit: int = 10):
    try:
        stmt = (
            select(
                (models.Game.id).label("game_id"),
                models.Game.name,
                models.GameStatistics.played_time,
            )
            .join(
                models.GameStatistics, models.Game.id == models.GameStatistics.game_id
            )
            .order_by(desc(models.GameStatistics.played_time))
            .limit(limit)
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e


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


def user_ratio(
    db: Session, season: int = current_season, is_active: bool | None = True
):
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

        ordered_data = sorted(data, key=lambda x: x["ratio"], reverse=True)
        return ordered_data
    except Exception as e:
        logger.error("Error calculating user ratio: " + str(e))
        raise e

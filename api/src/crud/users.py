import datetime
import json
from typing import Tuple, Union
import random

import bcrypt
from sqlalchemy import (
    asc,
    create_engine,
    desc,
    func,
    or_,
    select,
    text,
    update,
    extract,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# from sqlalchemy.util import immutabledict

from ..config import Config
from ..database import models, schemas
from ..utils import my_utils as utils
from ..utils.clockify_api import ClockifyApi
from . import games
from ..utils import ai_prompts as prompts
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify_api = ClockifyApi()
config = Config()
current_season = datetime.datetime.now().year

#################
##### USERS #####
#################


def create_admin_user(db: Session, username: str):
    try:
        db_user = db.query(models.User).filter(models.User.username == username).first()
        if db_user is None:
            salt = bcrypt.gensalt()
            default_password = config.DEFAULT_ADMIN_PASS
            # Hashing the password
            hashed_password = bcrypt.hashpw(default_password.encode("utf-8"), salt)
            db_user = models.User(
                username=username, is_admin=1, password=hashed_password, is_active=1
            )
            db.add(db_user)
            db.commit()
            logger.info("Admin user created")
        # else:
        #     logger.warning(username + " already exists as admin")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error creating admin user: " + str(e))
        if "Duplicate entry" not in str(e):
            logger.info(e)
        else:
            raise


def get_users(db: Session, is_active: bool = True) -> list[models.User]:
    """
    Get users based on their active status.

    Args:
        db (Session): DB Session
        is_active (bool | None): Filter by active status.
                                 True for active, False for inactive, None for all.

    Returns:
        list[models.User]: List of users based on the filter.
    """
    try:
        query = db.query(models.User)
        if is_active is True:  # Apply filter only if is_active is not None
            query = query.filter(models.User.is_active == is_active)
        return query.all()
    except SQLAlchemyError as e:
        logger.error("Error getting users: " + str(e))
        raise


def is_admin(db: Session, username: str) -> models.User:
    try:
        return (
            db.query(models.User)
            .filter(models.User.username == username, models.User.is_admin == 1)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error("Error checking is user is admin: " + str(e))
        raise


def is_active(db: Session, username: str) -> models.User:
    try:
        return (
            db.query(models.User)
            .filter(models.User.username == username, models.User.is_active == 1)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error("Error checking is user is active: " + str(e))
        raise


def get_user_by_username(db: Session, username: str) -> models.User:
    try:
        return db.query(models.User).filter(models.User.username == username).first()
    except SQLAlchemyError as e:
        logger.error("Error getting user by username: " + str(e))
        raise


def get_user_by_id(db: Session, id: int) -> models.User:
    try:
        return db.query(models.User).filter(models.User.id == id).first()
    except SQLAlchemyError as e:
        logger.error("Error getting user by id: " + str(e))
        raise


def get_user_by_clockify_id(db: Session, id: int) -> models.User:
    try:
        return db.query(models.User).filter(models.User.clockify_id == id).first()
    except SQLAlchemyError as e:
        logger.error("Error getting user by id: " + str(e))
        raise


def create_user(
    db: Session, user: schemas.UserCreate
) -> Union[Tuple[bool, models.User], Tuple[bool, int]]:
    # generating the salt
    salt = bcrypt.gensalt()

    # Check password length and email format
    if not utils.validate_email_format(user.email):
        return (False, 1)
    if not utils.validate_password_requirements(user.password):
        return (False, 0)

    # Hashing the password
    hashed_password = bcrypt.hashpw(user.password.encode("utf-8"), salt)

    try:
        logger.info("Creating new user: " + str(user.username))
        db_user = models.User(
            username=user.username,
            name=user.name,
            password=hashed_password,
            email=user.email,
        )
        db.add(db_user)
        db.commit()
        try:
            user_statistics = models.UserStatistics(
                user_id=db_user.id, current_ranking_hours=1000
            )
            db.add(user_statistics)
            db.commit()
        except Exception as e:
            db.rollback()
            if "Duplicate" not in str(e):
                logger.error("Error adding new game statistics: " + str(e))
                raise e
            else:
                logger.warning("User already exists in DB")
        return (True, -1)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error creating user: " + str(e))
        raise


def create_user_statistics(db: Session, user_id: id):
    try:
        user_statistics = models.UserStatistics(
            user_id=user_id, current_ranking_hours=1000
        )
        db.add(user_statistics)
        db.commit()
        db.refresh(user_statistics)

    except SQLAlchemyError as e:
        db.rollback()
        if "Duplicate" not in str(e):
            logger.error("Error creating user statistics: " + str(e))
            raise e


def create_user_statistics_historical(db: Session, user_id: id):
    try:
        user_statistics = models.UserStatisticsHistorical(
            user_id=user_id, current_ranking_hours=1000
        )
        db.add(user_statistics)
        db.commit()
        db.refresh(user_statistics)

    except SQLAlchemyError as e:
        db.rollback()
        if "Duplicate" not in str(e):
            logger.error("Error creating user statistics historical: " + str(e))
            raise e


def update_user(db: Session, user: schemas.UserUpdate):
    try:
        db_user = get_user_by_username(db, user.username)
        name = user.name if user.name is not None else db_user.name
        email = user.email if user.email is not None else db_user.email
        telegram_id = (
            user.telegram_id if user.telegram_id is not None else db_user.telegram_id
        )
        clockify_id = (
            user.clockify_id if user.clockify_id is not None else db_user.clockify_id
        )
        clockify_key = (
            user.clockify_key if user.clockify_key is not None else db_user.clockify_key
        )
        if user.password is not None:
            salt = bcrypt.gensalt()

            # Hashing the password
            hashed_password = bcrypt.hashpw(user.password.encode("utf-8"), salt)
            password = hashed_password
        else:
            password = db_user.password
        stmt = (
            update(models.User)
            .where(models.User.username == user.username)
            .values(
                telegram_id=telegram_id,
                name=name,
                email=email,
                password=password,
                clockify_id=clockify_id,
                clockify_key=clockify_key,
            )
        )
        db.execute(stmt)
        db.commit()
        return (
            db.query(models.User).filter(models.User.username == user.username).first()
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating user: " + str(e))
        raise


def update_user_as_admin(db: Session, user: schemas.UserUpdateForAdmin):
    try:
        db_user = get_user_by_username(db, user.username)
        name = user.name if user.name is not None else db_user.name
        email = user.email if user.email is not None else db_user.email
        telegram_id = (
            user.telegram_id if user.telegram_id is not None else db_user.telegram_id
        )
        is_admin = user.is_admin if user.is_admin is not None else db_user.is_admin
        is_active = user.is_active if user.is_active is not None else db_user.is_active
        clockify_id = (
            user.clockify_id if user.clockify_id is not None else db_user.clockify_id
        )
        clockify_key = (
            user.clockify_key if user.clockify_key is not None else db_user.clockify_key
        )
        if user.password is not None:
            salt = bcrypt.gensalt()

            # Hashing the password
            hashed_password = bcrypt.hashpw(user.password.encode("utf-8"), salt)
            password = hashed_password
        else:
            password = db_user.password
        stmt = (
            update(models.User)
            .where(models.User.username == user.username)
            .values(
                telegram_id=telegram_id,
                name=name,
                email=email,
                is_admin=is_admin,
                is_active=is_active,
                password=password,
                clockify_id=clockify_id,
                clockify_key=clockify_key,
            )
        )
        db.execute(stmt)
        db.commit()
        return (
            db.query(models.User).filter(models.User.username == user.username).first()
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating user: " + str(e))
        raise


def update_user_telegram_id(db: Session, user: schemas.TelegramUser):
    try:
        stmt = (
            update(models.User)
            .where(models.User.username == user.username)
            .values(
                telegram_id=user.telegram_id,
            )
        )
        db.execute(stmt)
        db.commit()
        return (
            db.query(models.User).filter(models.User.username == user.username).first()
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating TelegramID user: " + str(e))
        raise


def update_clockify_id(db: Session, username: str, user_clockify):
    if user_clockify is not None:
        try:
            clockify_id = user_clockify["id"]
            stmt = (
                update(models.User)
                .where(models.User.username == username)
                .values(
                    clockify_id=clockify_id,
                )
            )
            db.execute(stmt)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.error("Error updating user clockify_id: " + str(e))
            raise

    else:
        logger.info("User nor found in Clockify")


def upload_avatar(db: Session, username: str, avatar: bytes):
    try:
        stmt = (
            update(models.User)
            .where(models.User.username == username)
            .values(avatar=avatar)
        )
        db.execute(stmt)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error adding avatar: " + str(e))
        raise


def get_avatar(db: Session, username: str):
    try:
        return (
            db.query(models.User.avatar)
            .filter(models.User.username == username)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error("Error getting avatar: " + str(e))
        raise


async def add_new_game(
    db: Session,
    game: schemas.NewGameUser,
    user: models.User,
    start_date: str = None,
    season: int = current_season,
    silent: bool = False,
    from_sync=False,
) -> models.UserGame:
    logger.info("Adding new user game...")
    try:
        if start_date is None:
            started_date = datetime.datetime.now()
        else:
            started_date = utils.convert_date_from_text(start_date)
        game_db = games.get_game_by_id(db, game.game_id)
        if game_db is None:
            return None
        try:
            user_game = models.UserGame(
                game_id=game_db.id,
                user_id=user.id,
                completed=0,
                platform=game.platform,
                started_date=started_date,
                season=season,
            )
            db.add(user_game)
            db.commit()
            db.refresh(user_game)
        except SQLAlchemyError as e:
            db.rollback()
            if "Duplicate" not in str(e):
                logger.info("Error adding new user game: " + str(e))
                raise e
        played_games = count_played_games(db, user.id)
        if not from_sync:
            clockify_api.create_empty_time_entry(
                db, user.clockify_key, game_db.id, game.platform
            )
        started_game = (
            "[" + game_db.name + "](https://rawg.io/games/" + game_db.slug + ")"
        )
        msg = (
            "*"
            + user.name
            + "* acaba de empezar "
            + started_game
            + ", su juego número "
            + str(played_games)
            + " de este año."
        )
        await utils.send_message(
            msg,
            silent,
            openai=True,
            system_prompt=prompts.NEW_GAME_PROMPT,
        )
        logger.info("Game added!")
        return user_game
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error adding new game user: " + str(e))
        raise


def update_game(db: Session, game: models.UserGame, entry_id):
    current_year = datetime.datetime.now().year
    if current_year == current_season:
        try:
            stmt = (
                update(models.UserGame)
                .where(
                    models.UserGame.id == entry_id,
                    or_(
                        models.UserGame.platform == game.platform,
                    ),
                )
                .values(platform=game.platform)
            )
            db.execute(stmt)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            if "Duplicate" not in str(e):
                logger.error("Error updating game: " + str(e))
                raise e


def update_played_time_game(
    db: Session,
    user_id: str,
    game_id: str,
    time: int,
    season: int = current_season,
):
    try:
        stmt = (
            update(models.UserGame)
            .where(
                models.UserGame.game_id == game_id,
                models.UserGame.user_id == user_id,
                extract("year", models.UserGame.started_date) == season,
            )
            .values(played_time=time)
            .execution_options(synchronize_session="fetch")
        )
        db.execute(stmt)
        db.commit()
        # TODO: Check games time achievements
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating played time game: " + str(e))
        raise


def count_played_games(db: Session, user_id: int, season: int = current_season):
    try:
        return (
            db.query(models.UserGame).filter_by(user_id=user_id, season=season).count()
        )
    except SQLAlchemyError as e:
        logger.error("Error counting played games: " + str(e))
        raise e


def get_games(
    db: Session,
    user_id,
    limit=None,
    completed=None,
    season: int = current_season,
) -> list[schemas.UserGame]:
    if completed != None:
        completed = 1 if completed == True else 0
        stmt = (
            select(
                models.UserGame.__table__,
                models.UserGame.platform.label("platform_id"),
                models.Game.name.label("game_name"),
                models.PlatformTag.name.label("platform_name"),
                models.TimeEntry.start.label("last_played_time"),
            )
            .join(models.Game, models.UserGame.game_id == models.Game.id)
            .outerjoin(
                models.PlatformTag, models.UserGame.platform == models.PlatformTag.id
            )
            .join(
                models.TimeEntry,
                models.TimeEntry.project_clockify_id == models.Game.id,
            )
            .where(
                models.UserGame.user_id == user_id,
                models.UserGame.completed == completed,
                extract("year", models.UserGame.started_date) == season,
                models.UserGame.user_id == user_id,
                models.TimeEntry.user_id == user_id,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                models.UserGame.played_time,
                models.TimeEntry.start,
            )
            .order_by(desc(models.TimeEntry.start))
            .limit(limit)
        )
        result = db.execute(stmt).fetchall()
        unique_names = set()
        unique_data = []
        for item in result:
            if item["game_name"] not in unique_names:
                unique_names.add(item["game_name"])
                unique_data.append(item)
            if len(unique_data) == limit:
                break
        return unique_data

    else:
        stmt = (
            select(
                models.UserGame.__table__,
                models.UserGame.platform.label("platform_id"),
                models.Game.name.label("game_name"),
                models.PlatformTag.name.label("platform_name"),
                models.TimeEntry.start.label("last_played_time"),
            )
            .join(models.Game, models.UserGame.game_id == models.Game.id)
            .outerjoin(
                models.PlatformTag, models.UserGame.platform == models.PlatformTag.id
            )
            .join(
                models.TimeEntry,
                models.TimeEntry.project_clockify_id == models.Game.id,
            )
            .where(
                models.UserGame.user_id == user_id,
                extract("year", models.UserGame.started_date) == season,
                models.UserGame.user_id == user_id,
                models.TimeEntry.user_id == user_id,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                models.UserGame.played_time,
                models.TimeEntry.start,
            )
            .order_by(desc(models.TimeEntry.start))
            .limit(limit)
        )
        result = db.execute(stmt).fetchall()
        unique_names = set()
        unique_data = []
        for item in result:
            if item["game_name"] not in unique_names:
                unique_names.add(item["game_name"])
                unique_data.append(item)
            if len(unique_data) == limit:
                break
        return unique_data


def get_game_by_id(db: Session, user_id, game_id, season) -> models.UserGame:
    return (
        db.query(models.UserGame)
        .filter_by(user_id=user_id, game_id=game_id, season=season)
        .first()
    )


def update_played_days(
    db: Session, user_id: int, season_played_days: int, total_played_days: int = None
):
    try:
        stmt = (
            update(models.UserStatistics)
            .where(models.UserStatistics.user_id == user_id)
            .values(played_days=season_played_days)
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(e)
        raise e
    if total_played_days is not None:
        try:
            stmt = (
                update(models.UserStatisticsHistorical)
                .where(models.UserStatisticsHistorical.user_id == user_id)
                .values(played_days=total_played_days)
            )
            db.execute(stmt)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(e)
            raise e


def update_played_time(db: Session, user_id, played_time):
    # current_year = datetime.datetime.now().year
    try:
        # if current_year == current_season:
        stmt = (
            update(models.UserStatistics)
            .where(models.UserStatistics.user_id == user_id)
            .values(played_time=played_time)
        )
        db.execute(stmt)
        db.commit()
        # stmt = (
        #     update(models.UserStatisticsHistorical)
        #     .where(models.UserStatisticsHistorical.user_id == user_id)
        #     .values(played_time=played_time)
        # )
        # db.execute(stmt)
        # db.commit()
    except Exception as e:
        logger.error(e)
        raise e


def game_is_completed(db: Session, player, game, season: int = current_season) -> bool:
    stmt = select(models.UserGame).where(
        models.UserGame.game == game,
        models.UserGame.player == player,
        models.UserGame.completed == 1,
        extract("year", models.UserGame.started_date) == season,
    )
    game = db.execute(stmt).first()
    if game:
        return True
    return False


async def complete_game(
    db: Session,
    user_id,
    game_id,
    completed_date: str = None,
    season: int = current_season,
    silent: bool = False,
    from_sync=False,
):
    current_year = datetime.datetime.now().year
    try:
        db_game = games.get_game_by_id(db, game_id)
        user = get_user_by_id(db, user_id)
        user_game = get_game_by_id(db, user_id, db_game.id, current_year)
        game_info = await utils.get_game_info(db_game.name)
        if not from_sync:
            clockify_api.create_empty_time_entry(
                db,
                user.clockify_key,
                game_id,
                user_game.platform,
                completed=True,
            )
            return get_game_by_id(db, user_id, game_id, current_year)
        if completed_date is None:
            completed_date = datetime.datetime.now()
        else:
            completed_date = utils.convert_date_from_text(completed_date)
        stmt = (
            update(models.UserGame)
            .where(
                models.UserGame.game_id == game_id,
                models.UserGame.user_id == user_id,
                extract("year", models.UserGame.started_date) == season,
            )
            .values(
                completed=1,
                completed_date=completed_date,
            )
            .execution_options(synchronize_session="fetch")
        )
        db.execute(stmt)
        db.commit()
        logger.info("Game completed")
        if game_info["hltb"] is not None:
            avg_time = game_info["hltb"]["comp_main"]
        else:
            avg_time = 0
        games.update_avg_time_game(db, game_id, avg_time)
        game = games.get_game_by_id(db, game_id)
        num_completed_games = (
            db.query(models.UserGame.game_id)
            .filter_by(user_id=user_id, completed=1)
            .count()
        )
        completion_time = user_game.played_time
        message = (
            user.name
            + " acaba de completar su juego número "
            + str(num_completed_games)
            + ": *"
            + game.name
            + "* en "
            + str(utils.convert_time_to_hours(completion_time))
            + ". La media está en "
            + str(utils.convert_time_to_hours(avg_time))
            + "."
        )
        logger.info(message)
        new_games_recommendation = games.recommended_games(
            db, user_id, genres=game.genres
        )
        new_game = random.choice(new_games_recommendation)
        new_game_info = {}
        new_game_info["game"] = new_game[2]
        new_game_info["user"] = new_game[4]
        await utils.send_message(
            message,
            silent,
            openai=True,
            system_prompt=prompts.COMPLETED_GAME_PROMPT,
            new_game_recommended=new_game_info,
        )
        return get_game_by_id(db, user_id, game_id, current_year)

    except Exception as e:
        db.rollback()
        logger.error("Error completing game: " + str(e))
        raise e


async def rate_game(
    db: Session,
    user_id,
    game_id,
    score,
    season: int = current_season,
) -> models.UserGame:
    try:
        stmt = (
            update(models.UserGame)
            .where(
                models.UserGame.game_id == game_id,
                models.UserGame.user_id == user_id,
                extract("year", models.UserGame.started_date) == season,
            )
            .values(
                score=score,
            )
        )
        db.execute(stmt)
        db.commit()
        return get_game_by_id(db, user_id, game_id, season)

    except Exception as e:
        db.rollback()
        logger.error("Error rating game: " + str(e))
        raise e


def get_streaks(db: Session, username: str):
    try:
        user = get_user_by_username(db, username)
        return db.query(
            models.UserStatistics.current_streak,
            models.UserStatistics.best_streak,
            models.UserStatistics.best_streak_date,
        ).filter_by(user_id=user.id)
    except Exception as e:
        logger.error(e)
        raise e


def update_streaks(
    db: Session,
    user_id,
    current_streak,
    best_streak,
    best_streak_date,
    best_unplayed_streak,
    best_unplayed_streak_date,
    current_unplayed_streak,
):
    try:
        stmt = (
            update(models.UserStatistics)
            .where(models.UserStatistics.user_id == user_id)
            .values(
                current_streak=current_streak,
                best_streak=best_streak,
                best_streak_date=best_streak_date,
                best_unplayed_streak=best_unplayed_streak,
                best_unplayed_streak_date=best_unplayed_streak_date,
                current_unplayed_streak=current_unplayed_streak,
            )
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Error updating streaks: " + str(e))
        raise e


def played_time(
    db: Session, limit: int = None, is_active: bool | None = True
) -> list[models.UserStatistics]:
    query = (
        db.query(models.UserStatistics)
        .join(models.User, models.User.id == models.UserStatistics.user_id)
        .order_by(desc(models.UserStatistics.played_time))
    )

    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    if limit is not None:
        query = query.limit(limit)  # Aplica el límite si está definido

    return query.all()


def played_days(
    db: Session, limit: int = None, is_active: bool | None = True
) -> list[models.UserStatistics]:
    query = (
        db.query(models.UserStatistics)
        .join(models.User, models.User.id == models.UserStatistics.user_id)
        .order_by(desc(models.UserStatistics.played_days))
    )

    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    if limit is not None:
        query = query.limit(limit)  # Aplica el límite si está definido

    return query.all()


def current_ranking_hours(
    db: Session, limit: int = None, is_active: bool | None = True
) -> list[models.UserStatistics]:
    query = (
        db.query(models.UserStatistics)
        .join(models.User, models.User.id == models.UserStatistics.user_id)
        .order_by(asc(models.UserStatistics.current_ranking_hours))
    )

    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    if limit is not None:
        query = query.limit(limit)  # Aplica el límite si está definido

    return query.all()


def update_current_ranking_hours(db: Session, ranking, user_id):
    stmt = (
        update(models.UserStatistics)
        .where(models.UserStatistics.user_id == user_id)
        .values(current_ranking_hours=ranking)
    )
    db.execute(stmt)
    db.commit()


def activate_account(db: Session, username: str):
    try:
        logger.info("Activating account...")
        db_user = (
            db.query(models.User)
            .filter(models.User.username == username, models.User.is_active == 1)
            .first()
        )
        if db_user:
            return False
        stmt = (
            update(models.User)
            .where(models.User.username == username)
            .values(
                is_active=1,
            )
        )
        db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error("Error activating account: " + str(e))
        raise e


######################
##### STATISTICS #####
######################


def top_games(
    db: Session, username: str, limit: int = 10, season: int = current_season
):
    try:
        user = get_user_by_username(db, username)
        stmt = (
            select(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name.label("game_name"),
                models.UserGame.played_time.label("played_time"),
            )
            .join(models.User, models.User.id == models.UserGame.user_id)
            .join(models.Game, models.Game.id == models.UserGame.game_id)
            .where(
                models.UserGame.user_id == user.id,
                extract("year", models.UserGame.started_date) == season,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                models.UserGame.played_time,
            )
            .order_by(desc(models.UserGame.played_time))
            .limit(limit)
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error(e)
        raise e


# def played_games(db: Session, username: str, limit: int = None):
#     try:
#         user = get_user_by_username(db, username)
#         stmt = (
#             select(
#                 models.UserGame.user_id,
#                 models.UserGame.game_id,
#                 models.Game.name,
#                 models.TimeEntry.start.label("last_played_time"),
#                 models.UserGame.played_time,
#             )
#             .join(models.User, models.User.id == models.UserGame.user_id)
#             .join(models.Game, models.Game.id == models.UserGame.game_id)
#             .join(
#                 models.TimeEntry,
#                 models.TimeEntry.project_clockify_id == models.UserGame.game_id,
#             )
#             .where(
#                 models.UserGame.user_id == user.id, models.TimeEntry.user_id == user.id
#             )
#             .group_by(
#                 models.UserGame.user_id,
#                 models.UserGame.game_id,
#                 models.Game.name,
#                 models.UserGame.played_time,
#                 models.TimeEntry.start,
#             )
#             .order_by(desc(models.TimeEntry.start))
#         )
#         result = db.execute(stmt).fetchall()
#         unique_names = set()
#         unique_data = []
#         for item in result:
#             if item["name"] not in unique_names:
#                 unique_names.add(item["name"])
#                 unique_data.append(item)
#             if len(unique_data) == limit:
#                 break
#         return unique_data
#     except Exception as e:
#         logger.error(e)
#         raise e


# def completed_games(db: Session, username: str, limit: int = None):
#     try:
#         user = get_user_by_username(db, username)
#         stmt = (
#             select(
#                 models.UserGame.user_id,
#                 models.UserGame.game_id,
#                 models.Game.name,
#                 models.UserGame.completed_date.label("completed_date"),
#             )
#             .join(models.User, models.User.id == models.UserGame.user_id)
#             .join(models.Game, models.Game.id == models.UserGame.game_id)
#             .where(models.UserGame.user_id == user.id, models.UserGame.completed == 1)
#             .group_by(
#                 models.UserGame.user_id,
#                 models.UserGame.game_id,
#                 models.Game.name,
#                 # models.UserGame.played_time,
#             )
#             .order_by(desc(models.UserGame.completed_date))
#             .distinct()
#             .limit(limit)
#         )
#         return db.execute(stmt).fetchall()
#     except Exception as e:
#         logger.error(e)
#         raise e


def get_achievements(db: Session, username: str, season: int = current_season):
    try:
        user = get_user_by_username(db, username)
        stmt = (
            select(
                models.UserAchievement.user_id,
                models.UserAchievement.achievement_id,
                models.UserAchievement.date,
                models.Achievement.id,
                models.Achievement.title,
            )
            .join(models.User, models.User.id == models.UserAchievement.user_id)
            .join(
                models.Achievement,
                models.Achievement.id == models.UserAchievement.achievement_id,
            )
            .where(
                models.UserAchievement.user_id == user.id,
                models.UserAchievement.season == season,
            )
            .group_by(
                models.UserAchievement.user_id,
                models.UserAchievement.achievement_id,
                models.Achievement.id,
            )
            .order_by(asc(models.UserAchievement.date))
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e

import datetime
import json
from typing import Tuple, Union
import random

import bcrypt
from sqlalchemy import (
    and_,
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
from . import games
from ..utils import ai_prompts as prompts
from ..utils.logger import LogManager
from ..utils import seasons

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

#################
##### USERS #####
#################


GOD_USERNAME = "admin"
GOD_NAME = "Dios"


def ensure_god_user(db: Session):
    """
    Emergency administrator: make sure the "admin" user ("Dios") exists, is active,
    is admin and has the password defined in GOD_ADMIN_PASS. Runs on every API start,
    so restarting the API always restores access even if the account was altered.
    """
    if not config.GOD_ADMIN_PASS:
        raise ValueError("GOD_ADMIN_PASS must not be empty")
    try:
        hashed_password = bcrypt.hashpw(
            config.GOD_ADMIN_PASS.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        db_user = (
            db.query(models.User).filter(models.User.username == GOD_USERNAME).first()
        )
        if db_user is None:
            db.add(
                models.User(
                    name=GOD_NAME,
                    username=GOD_USERNAME,
                    password=hashed_password,
                    is_admin=1,
                    is_active=1,
                )
            )
            logger.info("God admin user created")
        else:
            db_user.name = GOD_NAME
            db_user.password = hashed_password
            db_user.is_admin = 1
            db_user.is_active = 1
            logger.info("God admin user restored")
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error ensuring god admin user: " + str(e))
        raise


def update_profile(db: Session, user: models.User, data: dict) -> models.User:
    """Update the self-service profile fields (only the ones present in data)."""
    try:
        for field in ("name", "email", "telegram_id"):
            if field in data:
                setattr(user, field, data[field])
        db.commit()
        db.refresh(user)
        return user
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error updating profile: " + str(e))
        raise


def change_password(db: Session, user: models.User, new_password: str):
    try:
        user.password = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error changing password: " + str(e))
        raise


def get_profile(db: Session, user: models.User, season: int = None) -> dict:
    """Main stats of a user for the profile page."""
    season = seasons.or_current(season)
    stats = (
        db.query(models.UserStatistics).filter_by(user_id=user.id).first()
    )
    played_time = (
        db.query(func.coalesce(func.sum(models.UserGame.played_time), 0))
        .filter(
            models.UserGame.user_id == user.id,
            models.UserGame.season == season,
        )
        .scalar()
    )
    achievements = get_achievements(db, user.username, season)
    return {
        "season": season,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "telegram_id": user.telegram_id,
        },
        "stats": {
            "played_time": int(played_time or 0),
            "played_days": (stats.played_days if stats else 0) or 0,
            "played_games": count_played_games(db, user.id, season),
            "completed_games": count_completed_games(db, user.id, season),
            "current_streak": (stats.current_streak if stats else 0) or 0,
            "best_streak": (stats.best_streak if stats else 0) or 0,
            "achievements": len(achievements),
        },
        "top_games": [
            {"game_id": r.game_id, "game_name": r.game_name, "played_time": r.played_time or 0}
            for r in top_games(db, user.username, limit=5, season=season)
        ],
        "achievements": [
            {"title": r.title, "date": r.date} for r in achievements[-5:][::-1]
        ],
    }


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


def get_user_by_login(db: Session, identifier: str) -> models.User | None:
    """
    Find the user that logs in with a username or an email.
    The username wins; the email match is case-insensitive and only counts
    when it is unambiguous (an email shared by two accounts logs nobody in).
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    user = get_user_by_username(db, identifier)
    if user:
        return user
    try:
        matches = (
            db.query(models.User)
            .filter(func.lower(models.User.email) == identifier.lower())
            .limit(2)
            .all()
        )
    except SQLAlchemyError as e:
        logger.error("Error getting user by email: " + str(e))
        raise
    return matches[0] if len(matches) == 1 else None


def email_in_use(db: Session, email: str, exclude_user_id: int | None = None) -> bool:
    """True if another account already has this email (case-insensitive)."""
    query = db.query(models.User.id).filter(
        func.lower(models.User.email) == email.strip().lower()
    )
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)
    return query.first() is not None


def telegram_id_in_use(db: Session, telegram_id: int, exclude_user_id: int | None = None) -> bool:
    """True if another account already uses this Telegram id."""
    query = db.query(models.User.id).filter(models.User.telegram_id == telegram_id)
    if exclude_user_id is not None:
        query = query.filter(models.User.id != exclude_user_id)
    return query.first() is not None


def get_user_by_id(db: Session, id: int) -> models.User:
    try:
        return db.query(models.User).filter(models.User.id == id).first()
    except SQLAlchemyError as e:
        logger.error("Error getting user by id: " + str(e))
        raise


def insert_user(
    db: Session,
    *,
    username: str,
    email: str,
    name: str | None,
    password: str,
    is_admin: bool = False,
    is_active: bool = False,
    telegram_id: int | None = None,
) -> models.User:
    """Insert a user (already validated) plus its statistics row."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        db_user = models.User(
            username=username,
            name=name,
            email=email,
            password=hashed,
            is_admin=int(is_admin),
            is_active=int(is_active),
            telegram_id=telegram_id,
        )
        db.add(db_user)
        db.flush()
        db.add(models.UserStatistics(user_id=db_user.id, current_ranking_hours=1000))
        db.commit()
        db.refresh(db_user)
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error inserting user: " + str(e))
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
    silent: bool = False,
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
    season: int = None,
):
    season = seasons.or_current(season)
    try:
        stmt = (
            update(models.UserGame)
            .where(
                models.UserGame.game_id == game_id,
                models.UserGame.user_id == user_id,
                models.UserGame.season == season,
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


def count_played_games(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    try:
        return (
            db.query(models.UserGame).filter_by(user_id=user_id, season=season).count()
        )
    except SQLAlchemyError as e:
        logger.error("Error counting played games: " + str(e))
        raise e


def count_completed_games(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    try:
        return (
            db.query(models.UserGame)
            .filter_by(user_id=user_id, completed=1, season=season)
            .count()
        )
    except SQLAlchemyError as e:
        logger.error("Error counting completed games: " + str(e))
        raise e


def get_games(
    db: Session,
    user_id,
    limit=None,
    completed=None,
    season: int = None,
) -> list[schemas.UserGame]:
    season = seasons.or_current(season)
    # Local import to avoid a circular import (crud.time_entries imports crud.users).
    from . import time_entries as time_entries_crud

    sessions = time_entries_crud.sessions_subquery()
    if completed != None:
        completed = 1 if completed == True else 0
        stmt = (
            select(
                models.UserGame.__table__,
                models.UserGame.platform.label("platform_id"),
                models.Game.name.label("game_name"),
                models.PlatformTag.name.label("platform_name"),
                sessions.c.start.label("last_played_time"),
            )
            .join(models.Game, models.UserGame.game_id == models.Game.id)
            .outerjoin(
                models.PlatformTag, models.UserGame.platform == models.PlatformTag.id
            )
            .outerjoin(
                sessions,
                (sessions.c.game_id == models.Game.id)
                & (sessions.c.user_id == models.UserGame.user_id),
            )
            .where(
                models.UserGame.user_id == user_id,
                models.UserGame.completed == completed,
                models.UserGame.season == season,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                models.UserGame.played_time,
                sessions.c.start,
            )
            .order_by(desc(sessions.c.start))
            .limit(limit)
        )
        # .mappings() so `item["game_name"]` string-key access works
        # (SQLAlchemy 2.x plain Row only supports it via _mapping/.mappings()).
        result = db.execute(stmt).mappings().fetchall()
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
                sessions.c.start.label("last_played_time"),
            )
            .join(models.Game, models.UserGame.game_id == models.Game.id)
            .outerjoin(
                models.PlatformTag, models.UserGame.platform == models.PlatformTag.id
            )
            .outerjoin(
                sessions,
                (sessions.c.game_id == models.Game.id)
                & (sessions.c.user_id == models.UserGame.user_id),
            )
            .where(
                models.UserGame.user_id == user_id,
                models.UserGame.season == season,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                models.UserGame.played_time,
                sessions.c.start,
            )
            .order_by(desc(sessions.c.start))
            .limit(limit)
        )
        result = db.execute(stmt).mappings().fetchall()
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


def update_played_days(db: Session, user_id: int, season_played_days: int):
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


def update_played_time(db: Session, user_id, played_time):
    try:
        stmt = (
            update(models.UserStatistics)
            .where(models.UserStatistics.user_id == user_id)
            .values(played_time=played_time)
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        logger.error(e)
        raise e


def game_is_completed(db: Session, player, game, season: int = None) -> bool:
    season = seasons.or_current(season)
    stmt = select(models.UserGame).where(
        models.UserGame.game == game,
        models.UserGame.player == player,
        models.UserGame.completed == 1,
        models.UserGame.season == season,
    )
    game = db.execute(stmt).first()
    if game:
        return True
    return False


# ── Library: every game of a user, with its completion state ──


def _last_played_by_year():
    """Latest session start per (user, game, season)."""
    return (
        select(
            models.GameTimer.user_id.label("user_id"),
            models.GameTimer.game_id.label("game_id"),
            models.GameTimer.season.label("season"),
            func.max(models.GameTimer.start_time).label("last_played"),
        )
        .group_by(models.GameTimer.user_id, models.GameTimer.game_id, models.GameTimer.season)
        .subquery("last_played")
    )


def _completed_keys(db: Session, user_id: int) -> set:
    """(game_id, season) pairs the user has already completed."""
    rows = (
        db.query(models.UserGame.game_id, models.UserGame.season)
        .filter(models.UserGame.user_id == user_id, models.UserGame.completed == 1)
        .all()
    )
    return {(r.game_id, r.season) for r in rows}


def completed_in_season(db: Session, user_id: int, game_id: str, season: int) -> bool:
    return (game_id, season) in _completed_keys(db, user_id)


def _library_query(user_id: int, entry_id: int | None = None):
    last = _last_played_by_year()
    stmt = (
        select(
            models.UserGame,
            models.Game.name.label("game_name"),
            models.Game.image_url.label("image_url"),
            models.PlatformTag.name.label("platform_name"),
            last.c.last_played.label("last_played"),
        )
        .join(models.Game, models.Game.id == models.UserGame.game_id)
        .outerjoin(models.PlatformTag, models.PlatformTag.id == models.UserGame.platform)
        .outerjoin(
            last,
            and_(
                last.c.user_id == models.UserGame.user_id,
                last.c.game_id == models.UserGame.game_id,
                last.c.season == models.UserGame.season,
            ),
        )
        .where(models.UserGame.user_id == user_id)
    )
    if entry_id is not None:
        stmt = stmt.where(models.UserGame.id == entry_id)
    # most recently played first; entries without sessions go last (by start date)
    return stmt.order_by(
        last.c.last_played.is_(None),
        last.c.last_played.desc(),
        models.UserGame.started_date.desc(),
        models.UserGame.id.desc(),
    )


def _library_item(row, completed_keys: set, current_season: int) -> dict:
    entry = row.UserGame
    done = bool(entry.completed)
    # why a pending entry cannot be completed (None when it can)
    blocked = None
    if not done:
        if entry.season != current_season:
            blocked = "closed_season"
        elif (entry.game_id, entry.season) in completed_keys:
            blocked = "completed_in_season"
    return {
        "id": entry.id,
        "game_id": entry.game_id,
        "game_name": row.game_name,
        "image_url": row.image_url,
        "platform_id": entry.platform,
        "platform_name": row.platform_name,
        "season": entry.season,
        "started_date": entry.started_date,
        "last_played": row.last_played,
        "played_time": entry.played_time or 0,
        "completed": done,
        "completed_date": entry.completed_date,
        # a game can be completed once per season, and only in the running one
        "can_complete": not done and blocked is None,
        "complete_blocked": blocked,  # "closed_season" | "completed_in_season" | None
    }


def get_library(db: Session, user_id: int, limit: int = 15, offset: int = 0) -> dict:
    season = seasons.current()
    total = db.query(models.UserGame).filter(models.UserGame.user_id == user_id).count()
    rows = db.execute(_library_query(user_id).limit(limit).offset(offset)).all()
    keys = _completed_keys(db, user_id)
    return {
        "season": season,
        "total": total,
        "items": [_library_item(r, keys, season) for r in rows],
    }


def get_library_item(db: Session, user_id: int, entry_id: int) -> dict | None:
    row = db.execute(_library_query(user_id, entry_id)).first()
    if row is None:
        return None
    return _library_item(row, _completed_keys(db, user_id), seasons.current())


def get_library_entry(db: Session, user_id: int, entry_id: int) -> models.UserGame | None:
    return db.query(models.UserGame).filter_by(id=entry_id, user_id=user_id).first()


def uncomplete_entry(db: Session, entry: models.UserGame):
    """Unmark a completion. The entry itself (time played, sessions) stays."""
    try:
        entry.completed = 0
        entry.completed_date = None
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error unmarking completion: " + str(e))
        raise


def set_completed_date(db: Session, entry: models.UserGame, completed_date: datetime.date):
    try:
        entry.completed_date = completed_date
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error changing completion date: " + str(e))
        raise


async def complete_entry(
    db: Session,
    entry: models.UserGame,
    completed_date: datetime.date | None = None,
    silent: bool = False,
) -> models.UserGame:
    """
    Mark one library entry as completed. The completion is saved first; the
    follow-ups (average time, achievements, group announcement) are best
    effort and never undo it.
    """
    try:
        entry.completed = 1
        entry.completed_date = completed_date or datetime.date.today()
        db.commit()
        logger.info("Game completed")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error completing game: " + str(e))
        raise
    try:
        await _after_completion(db, entry, silent)
    except Exception as e:
        logger.error("Error in post-completion tasks: " + str(e))
    return entry


async def _after_completion(db: Session, entry: models.UserGame, silent: bool):
    game = games.get_game_by_id(db, entry.game_id)
    user = get_user_by_id(db, entry.user_id)
    game_info = await utils.get_game_info(game.name)
    avg_time = game_info["hltb"]["comp_main"] if game_info["hltb"] is not None else 0
    games.update_avg_time_game(db, entry.game_id, avg_time)
    game = games.get_game_by_id(db, entry.game_id)
    completion_time = entry.played_time

    # Local import to avoid a circular import (crud.achievements imports crud.users).
    from .achievements import Achievements

    await Achievements().just_in_time(
        db, user, completion_time, avg_time, entry.game_id, silent=silent
    )

    message = (
        user.name
        + " acaba de completar su juego número "
        + str(count_completed_games(db, user.id, entry.season))
        + ": *"
        + game.name
        + "* en "
        + str(utils.convert_time_to_hours(completion_time))
        + ". La media está en "
        + str(utils.convert_time_to_hours(avg_time))
        + "."
    )
    logger.info(message)
    new_game_info = {}
    suggestions = games.recommended_games(db, entry.user_id, genres=game.genres)
    if suggestions:
        new_game = random.choice(suggestions)
        new_game_info = {"game": new_game[2], "user": new_game[4]}
    await utils.send_message(
        message,
        silent,
        openai=True,
        system_prompt=prompts.COMPLETED_GAME_PROMPT,
        new_game_recommended=new_game_info,
    )


async def complete_game(
    db: Session,
    user_id,
    game_id,
    completed_date: str = None,
    season: int = None,
    silent: bool = False,
):
    """Complete the pending entry of a game in a season (current by default)."""
    season = seasons.or_current(season)
    entry = (
        db.query(models.UserGame)
        .filter(
            models.UserGame.user_id == user_id,
            models.UserGame.game_id == game_id,
            models.UserGame.season == season,
            models.UserGame.completed != 1,
        )
        .order_by(models.UserGame.id)
        .first()
    )
    if entry is None:
        return get_game_by_id(db, user_id, game_id, season)
    parsed = utils.convert_date_from_text(completed_date) if completed_date else None
    return await complete_entry(db, entry, parsed, silent)


async def rate_game(
    db: Session,
    user_id,
    game_id,
    score,
    season: int = None,
) -> models.UserGame:
    season = seasons.or_current(season)
    try:
        stmt = (
            update(models.UserGame)
            .where(
                models.UserGame.game_id == game_id,
                models.UserGame.user_id == user_id,
                models.UserGame.season == season,
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


def top_games(db: Session, username: str, limit: int = 10, season: int = None):
    season = seasons.or_current(season)
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
                models.UserGame.season == season,
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


def get_achievements(db: Session, username: str, season: int = None):
    season = seasons.or_current(season)
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

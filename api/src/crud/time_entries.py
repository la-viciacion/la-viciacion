import datetime
from typing import Union, Tuple

from sqlalchemy import (
    asc,
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
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.clockify_api import ClockifyApi
from . import clockify, games, users
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify_api = ClockifyApi()
config = Config()
current_season = datetime.datetime.now().year


def get_users_played_time(db: Session, season: int = current_season):
    stmt = (
        select(models.TimeEntry.user_id, func.sum(models.TimeEntry.duration))
        .where(extract("year", models.TimeEntry.start) == season)
        .group_by(models.TimeEntry.user_id)
    )
    return db.execute(stmt)


def get_user_played_time(db: Session, user_id: str, season: int = current_season):
    stmt = (
        select(
            models.TimeEntry.user_id,
            func.sum(models.TimeEntry.duration),
        )
        .where(
            models.TimeEntry.user_id == user_id,
            extract("year", models.TimeEntry.start) == season,
        )
        .group_by(models.TimeEntry.user_id)
    )
    return db.execute(stmt).first()


def get_games_played_time(
    db: Session, season: int = current_season, is_active: bool = True
):
    stmt = (
        select(
            models.TimeEntry.project_clockify_id, func.sum(models.TimeEntry.duration)
        )
        .join(models.User, models.TimeEntry.user_id == models.User.id)
        .where(
            extract("year", models.TimeEntry.start) == season,
            models.User.is_active == is_active,
        )
        .group_by(models.TimeEntry.project_clockify_id)
    )
    result = db.execute(stmt)
    return result


def get_time_entry_by_date(
    db: Session, user_id: int, date: str, mode: int
) -> list[models.TimeEntry]:
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        date (str): _description_
        mode (int): 1==, 2<=, 3>=

    Returns:
        _type_: _description_
    """
    if mode == 1:
        return db.query(models.TimeEntry).filter(
            models.TimeEntry.user_id == user_id,
            or_(
                func.DATE(models.TimeEntry.start) == date,
                func.DATE(models.TimeEntry.end) == date,
            ),
        )
    elif mode == 2:
        return db.query(models.TimeEntry).filter(
            models.TimeEntry.user_id == user_id,
            or_(
                func.DATE(models.TimeEntry.start) <= date,
                func.DATE(models.TimeEntry.end) <= date,
            ),
        )
    elif mode == 3:
        return db.query(models.TimeEntry).filter(
            models.TimeEntry.user_id == user_id,
            or_(
                func.DATE(models.TimeEntry.start) >= date,
                func.DATE(models.TimeEntry.end) >= date,
            ),
        )


def get_user_games_played_time(
    db: Session, user_id: str, game_id: str = None, season: int = current_season
) -> list[models.TimeEntry]:
    if game_id is not None:
        return (
            db.query(
                models.TimeEntry.project_clockify_id,
                func.sum(models.TimeEntry.duration),
            )
            .filter(
                models.TimeEntry.user_id == user_id,
                extract("year", models.TimeEntry.start) == season,
            )
            .filter(models.TimeEntry.project_clockify_id == game_id)
            .group_by(models.TimeEntry.project_clockify_id)
            .all()
        )
    else:
        return (
            db.query(
                models.TimeEntry.project_clockify_id,
                func.sum(models.TimeEntry.duration),
            )
            .filter(
                models.TimeEntry.user_id == user_id,
                extract("year", models.TimeEntry.start) == season,
            )
            .group_by(models.TimeEntry.project_clockify_id)
            .all()
        )


def get_time_entries(
    db: Session, start_date: str = None, season: int = current_season
) -> list[models.TimeEntry]:
    if start_date:
        # logger.debug(start_date)
        return (
            db.query(models.TimeEntry)
            .filter(models.TimeEntry.start >= start_date)
            .order_by(models.TimeEntry.user_id)
        )
    else:
        return (
            db.query(models.TimeEntry)
            .filter(extract("year", models.TimeEntry.start) == season)
            .order_by(models.TimeEntry.user_id)
        )


def get_time_entries_by_user(
    db: Session,
    user_id: int,
    start_date: str = None,
    season: int = current_season,
) -> list[models.TimeEntry]:
    if start_date:
        # logger.debug(start_date)
        return db.query(models.TimeEntry).filter(
            models.TimeEntry.user_id == user_id,
            models.TimeEntry.start >= start_date,
        )
    else:
        # logger.debug("Get ALL time entries for user " + str(user_id))
        time_entries = (
            db.query(models.TimeEntry)
            .filter(
                models.TimeEntry.user_id == user_id,
                extract("year", models.TimeEntry.start) == season,
            )
            .order_by(models.TimeEntry.project_clockify_id)
            .all()
        )
        return time_entries


def get_played_days(
    db: Session,
    user_id: int,
    start_date: str = None,
    end_date: str = None,
    season: int = current_season,
) -> list[models.TimeEntry]:
    played_days = []
    real_played_days = []
    if start_date is None:
        current_date = datetime.datetime.now()
        start_date = str(current_date.year) + "-01-01"
    if end_date is None:
        end_date = "3000-12-31"
    played_start_days = (
        db.query(func.DATE(models.TimeEntry.start))
        .filter(models.TimeEntry.user_id == user_id)
        .filter(func.DATE(models.TimeEntry.start) >= start_date)
        .filter(func.DATE(models.TimeEntry.start) <= end_date)
        .filter(extract("year", models.TimeEntry.start) == season)
        .filter(models.TimeEntry.duration >= 600)
        # .filter(or_(models.TimeEntry.duration >= 600, models.TimeEntry.duration == None))
        .distinct()
        .all()
    )
    played_end_days = (
        db.query(func.DATE(models.TimeEntry.end))
        .filter(models.TimeEntry.user_id == user_id)
        .filter(func.DATE(models.TimeEntry.end) >= start_date)
        .filter(func.DATE(models.TimeEntry.end) <= end_date)
        .filter(extract("year", models.TimeEntry.start) == season)
        .filter(models.TimeEntry.duration >= 600)
        # .filter(or_(models.TimeEntry.duration >= 600, models.TimeEntry.duration == None))
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


async def sync_clockify_entries_db(
    db: Session, user: models.User, entries, only_time_entries: bool, silent: bool
):
    # current_season = datetime.datetime.now().year
    for entry in entries:
        if entry["projectId"] is None:
            logger.warning("Time entry without project: " + str(entry["id"]))
            # msg = (
            #     "Hola, "
            #     + user.name
            #     + ". Tienes un timer activo sin juego. Acuérdate de añadirlo antes de pararlo."
            # )
            # await utils.send_message_to_user(user.telegram_id, msg)
            continue
        try:
            # Extract data from time entry
            start = entry["timeInterval"]["start"]
            end = entry["timeInterval"]["end"]
            duration = entry["timeInterval"]["duration"]
            platform = None
            completed = None
            if entry["tagIds"] is not None and len(entry["tagIds"]) > 0:
                for tag in entry["tagIds"]:
                    platform_check = clockify.get_platform_by_tag_id(db, tag)
                    completed_check = clockify.check_completed_tag_by_id(db, tag)
                    if completed is None and completed_check is not None:
                        completed = 1
                    if platform is None and platform_check is not None:
                        platform = tag

            start = utils.change_timezone_clockify(start)
            if end is not None and end != "":
                end = utils.change_timezone_clockify(end)
            else:
                end = None

            # Check if time entry already exists (to update it if needed)
            stmt = select(models.TimeEntry).where(models.TimeEntry.id == entry["id"])
            exists = db.execute(stmt).first()
            # Create new time entry
            if not exists:
                try:
                    if end is not None:
                        new_entry = models.TimeEntry(
                            id=entry["id"],
                            user_id=user.id,
                            user_clockify_id=user.clockify_id,
                            project_clockify_id=entry["projectId"],
                            start=start,
                            end=end,
                            duration=utils.convert_clockify_duration(duration),
                        )
                    else:
                        new_entry = models.TimeEntry(
                            id=entry["id"],
                            user_id=user.id,
                            user_clockify_id=user.clockify_id,
                            project_clockify_id=entry["projectId"],
                            start=start,
                        )
                    db.add(new_entry)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(
                        "Error creating time entry " + str(entry) + ": " + str(e)
                    )
            # Update existing time entry
            else:
                try:
                    if end is not None:
                        stmt = (
                            update(models.TimeEntry)
                            .where(models.TimeEntry.id == entry["id"])
                            .values(
                                project_clockify_id=entry["projectId"],
                                start=start,
                                end=end,
                                duration=utils.convert_clockify_duration(duration),
                            )
                        )
                    else:
                        stmt = (
                            update(models.TimeEntry)
                            .where(models.TimeEntry.id == entry["id"])
                            .values(
                                project_clockify_id=entry["projectId"],
                                start=start,
                            )
                        )
                    db.execute(stmt)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(
                        "Error updating time entry " + str(entry) + ": " + str(e)
                    )

            if only_time_entries:
                continue
            # Check if game on clockify already exists on local DB
            game = games.get_game_by_id(db, entry["projectId"])
            if game is not None:
                game_name = game.name
                game_id = game.id
            else:
                logger.info("Project " + entry["projectId"] + " not in DB")
                project = clockify_api.get_project_by_id(entry["projectId"])
                # logger.debug("Clockify project:")
                # logger.debug(project)
                game_name = project["name"]
                new_game_info = await utils.get_new_game_info(project)
                # logger.debug("New game info:")
                # logger.debug(new_game_info.__dict__)
                new_game = await games.new_game(db, new_game_info)
                game_id = new_game.id

            # Add game to GameStatistics (if needed)
            try:
                games.create_game_statistics(db, game_id)
                games.create_game_statistics_historical(db, game_id)
            except Exception as e:
                logger.error(
                    "Error creating game statistics for " + game_name + ": " + str(e)
                )

            # Check if player already plays the game this season
            # if time_entry_year == config.CURRENT_SEASON:
            already_playing = users.get_game_by_id(db, user.id, game_id, current_season)
            if not already_playing:
                try:
                    logger.info("User not playing " + game_name)
                    new_user_game = schemas.NewGameUser(
                        game_id=game_id, platform=platform
                    )
                    await users.add_new_game(
                        db,
                        game=new_user_game,
                        user=user,
                        start_date=start,
                        silent=silent,
                        from_sync=True,
                    )
                    already_playing = users.get_game_by_id(
                        db, user.id, game_id, current_season
                    )
                except Exception as e:
                    logger.error("Error adding game " + game_name + ": " + str(e))
            try:
                if platform is not None and already_playing.platform != platform:
                    try:
                        stmt = (
                            update(models.UserGame)
                            .where(models.UserGame.id == already_playing.id)
                            .values(
                                platform=platform,
                            )
                        )
                        db.execute(stmt)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.error(
                            "Error updating platform for " + game_name + ": " + str(e)
                        )
            except Exception as e:
                logger.error("Error updating platform for " + game_name + ": " + str(e))
            if completed is not None and already_playing.completed != 1:
                try:
                    logger.info("Completing game " + str(game.id) + "...")
                    played_time = get_user_games_played_time(db, user.id, game.id)
                    # The follow list only will have 1 item
                    for played_game in played_time:
                        users.update_played_time_game(
                            db, user.id, played_game[0], played_game[1]
                        )
                    await users.complete_game(
                        db,
                        user.id,
                        game.id,
                        completed_date=start,
                        silent=silent,
                        from_sync=True,
                    )
                except Exception as e:
                    logger.error("Error completing game " + game_name + ": " + str(e))
            try:
                update_game = models.UserGame(platform=platform)
                users.update_game(db, update_game, already_playing.id)
            except Exception as e:
                logger.error("Error updating game" + game_name + " for user: " + str(e))

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Error adding time entry " + str(entry) + ": " + str(e))


def get_time_entry_by_time(
    db: Session,
    user_id: int,
    duration: int,
    mode: int,
    season: int = current_season,
) -> models.TimeEntry:
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        duration (int): _description_
        mode (int): 1==, 2<=, 3>=

    Returns:
        _type_: _description_
    """
    if mode == 1:
        time_entry = (
            db.query(models.TimeEntry)
            .filter(
                models.TimeEntry.user_id == user_id,
                models.TimeEntry.duration == duration,
                extract("year", models.TimeEntry.start) == season,
            )
            .first()
        )
    elif mode == 2:
        time_entry = (
            db.query(models.TimeEntry)
            .filter(
                models.TimeEntry.user_id == user_id,
                models.TimeEntry.duration <= duration,
                extract("year", models.TimeEntry.start) == season,
            )
            .first()
        )
    elif mode == 3:
        time_entry = (
            db.query(models.TimeEntry)
            .filter(
                models.TimeEntry.user_id == user_id,
                models.TimeEntry.duration >= duration,
                extract("year", models.TimeEntry.start) == season,
            )
            .first()
        )
    return time_entry


def get_played_time_by_day(db: Session, user_id: int, season: int = current_season):
    played_start_days = (
        db.query(func.DATE(models.TimeEntry.start), func.sum(models.TimeEntry.duration))
        .filter(
            models.TimeEntry.user_id == user_id,
            extract("year", models.TimeEntry.start) == season,
        )
        .group_by(func.DATE(models.TimeEntry.start))
        .all()
    )
    return sorted(played_start_days)


def get_time_entry_between_hours(
    db: Session,
    user_id: int,
    start_hour: int,
    end_hour: int,
    season: int = current_season,
) -> list[models.TimeEntry]:
    """_summary_

    Args:
        db (Session): _description_
        user_id (int): _description_
        start_hour (int): Include this hour
        end_hour (int): Exclude this hour (search until 1 minute before)

    Returns:
        list[models.TimeEntry]: _description_
    """
    time_entries = (
        db.query(models.TimeEntry)
        .filter(models.TimeEntry.user_id == user_id)
        .filter(extract("hour", models.TimeEntry.start) >= start_hour)
        .filter(extract("hour", models.TimeEntry.start) < end_hour)
        .filter(extract("year", models.TimeEntry.start) == season)
        .all()
    )
    return time_entries


def get_active_time_entry_by_user(db: Session, user: models.User) -> models.TimeEntry:
    active_time_entry = (
        db.query(models.TimeEntry)
        .filter(models.TimeEntry.end == None)
        .filter(models.TimeEntry.user_clockify_id == user.clockify_id)
        .first()
    )
    return active_time_entry


def get_forgotten_timer_by_user(db: Session, user: models.User):
    current_time = datetime.datetime.now()
    time_threshold = current_time - datetime.timedelta(hours=4)
    active_time_entry = (
        db.query(models.TimeEntry)
        .filter(models.TimeEntry.user_clockify_id == user.clockify_id)
        .filter(models.TimeEntry.duration.is_(None))
        .filter(models.TimeEntry.start < time_threshold)
        .first()
    )
    return active_time_entry


def get_older_active_timers(
    db: Session, user: models.User = None
) -> list[models.TimeEntry]:
    current_time = datetime.datetime.now()
    time_threshold = current_time - datetime.timedelta(minutes=5)
    if user is None:
        active_time_entries = (
            db.query(models.TimeEntry)
            .filter(models.TimeEntry.duration.is_(None))
            .filter(models.TimeEntry.start < time_threshold)
            .all()
        )
    else:
        active_time_entries = (
            db.query(models.TimeEntry)
            .filter(models.TimeEntry.user_clockify_id == user.clockify_id)
            .filter(models.TimeEntry.duration.is_(None))
            .filter(models.TimeEntry.start < time_threshold)
            .all()
        )
    return active_time_entries


def get_older_timers(db: Session, user: models.User = None) -> list[models.TimeEntry]:
    current_time = datetime.datetime.now()
    time_threshold = current_time - datetime.timedelta(minutes=5)
    if user is None:
        active_time_entries = (
            db.query(models.TimeEntry)
            .filter(models.TimeEntry.start < time_threshold)
            .all()
        )
    else:
        active_time_entries = (
            db.query(models.TimeEntry)
            .filter(models.TimeEntry.user_clockify_id == user.clockify_id)
            .filter(models.TimeEntry.start < time_threshold)
            .all()
        )
    return active_time_entries


def get_weekly_resume(
    db: Session, user: models.User, weeks_ago: int = 0
) -> list[models.TimeEntry]:
    """_summary_

    Args:
        db (Session): _description_
        user (models.User): _description_
        mode (int, optional): 0 = last week. 1 = current week. Defaults to 0.

    Returns:
        list[models.TimeEntry]: _description_
    """
    # if mode == 0:
    #     first_day, last_day = utils.get_last_week_range_dates()
    #     first_day, last_day = utils.get_week_range_dates(1)
    # else:
    #     first_day, last_day = utils.get_current_week_range_dates()
    first_day, last_day = utils.get_week_range_dates(weeks_ago)
    weekly_hours = (
        db.query(
            func.sum(models.TimeEntry.duration),
            func.count(models.TimeEntry.id),
            func.count(func.distinct(models.TimeEntry.project_clockify_id)),
        )
        .filter(models.TimeEntry.user_id == user.id)
        .filter(func.DATE(models.TimeEntry.start) >= first_day)
        .filter(func.DATE(models.TimeEntry.start) <= last_day)
        .filter(models.TimeEntry.duration > 0)
        .all()
    )
    return weekly_hours


def delete_time_entry(db: Session, time_entry_id: str):
    try:
        db.query(models.TimeEntry).filter(models.TimeEntry.id == time_entry_id).delete()
        db.commit()
    except Exception as e:
        logger.error(e)

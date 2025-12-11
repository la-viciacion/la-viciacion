import datetime
from typing import Union
import random

from sqlalchemy import asc, create_engine, delete, desc, func, select, text, update, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import models, schemas
from ..utils import actions
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.clockify_api import ClockifyApi
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify_api = ClockifyApi()

#################
##### GAMES #####
#################


def get_games(db: Session, limit: int = None) -> list[models.Game]:
    return db.query(models.Game).limit(limit)


def get_game_by_name(db: Session, name: str) -> list[models.Game]:
    logger.info("Searching game by name: " + name)
    search = "%{}%".format(name)
    return db.query(models.Game).filter(models.Game.name.like(search))


def get_game_by_id(db: Session, game_id: int) -> models.Game:
    return db.query(models.Game).filter(models.Game.id == game_id).first()


def recommended_games(
    db: Session, user_id: int, genres: list[str] = [], limit: int = None
):
    genres_filter = [models.Game.genres.ilike(f"%{genre}%") for genre in genres]
    unplayed_games = (
        db.query(
            models.UserGame.game_id,
            models.UserGame.user_id,
            models.Game.name,
            models.Game.genres,
            models.User.name,
        )
        .join(models.Game, models.UserGame.game_id == models.Game.id)
        .join(models.User, models.UserGame.user_id == models.User.id)
        .filter(models.UserGame.user_id != user_id)
        .filter(or_(*genres_filter))
        .limit(limit)
    )
    recommended_games = []
    for game in unplayed_games:
        recommended_games.append(game)
    random.shuffle(recommended_games)
    unique_recommended_games = []
    seen_game_ids = set()

    for game in recommended_games:
        if game[0] not in seen_game_ids:
            unique_recommended_games.append(game)
            seen_game_ids.add(game[0])
    return unique_recommended_games


async def new_game(db: Session, game: schemas.NewGame) -> models.Game:
    logger.info("Adding new game to DB: " + game.name)
    if game.clockify_id is None or not utils.check_hex(game.clockify_id):
        logger.info("No clockify ID. Adding to clockify...")
        clockify_id = clockify_api.add_project(game.name)["id"]
        new_game = {"name": game.name, "id": clockify_id}
        game_info = await utils.get_new_game_info(new_game)
        game_to_add = models.Game(
            id=clockify_id,
            name=game_info.name,
            dev=game_info.dev,
            steam_id=game_info.steam_id,
            image_url=game_info.image_url,
            release_date=game_info.release_date,
            genres=game_info.genres,
            avg_time=game_info.avg_time,
            slug=game_info.slug,
        )
    else:
        game_to_add = models.Game(
            id=game.clockify_id,
            name=game.name,
            dev=game.dev,
            steam_id=game.steam_id,
            image_url=game.image_url,
            release_date=game.release_date,
            genres=game.genres,
            avg_time=game.avg_time,
            slug=game.slug,
        )
    try:
        db.add(game_to_add)
        db.commit()
        db.refresh(game_to_add)
        game_added = game_to_add
        try:
            game_statistics = models.GameStatistics(
                game_id=game_added.id, current_ranking=100000000
            )
            db.add(game_statistics)
            db.commit()
        except Exception as e:
            db.rollback()
            if "Duplicate" not in str(e):
                logger.error("Error adding new game statistics: " + str(e))
                raise e
        logger.info("Game added to DB")
        return game_added
    except Exception as e:
        logger.error("Error adding new game: " + str(e))
        db.rollback()
        if "Duplicate" not in str(e):
            logger.warning("Error adding new game: " + str(e))
            raise e


def create_game_statistics(db: Session, game_id: int):
    try:
        game_statistics = models.GameStatistics(
            game_id=game_id, current_ranking=1000000
        )
        db.add(game_statistics)
        db.commit()
        db.refresh(game_statistics)

    except SQLAlchemyError as e:
        db.rollback()
        if "Duplicate" not in str(e):
            logger.info("Error creating games statistics: " + str(e))
            raise e


def create_game_statistics_historical(db: Session, game_id: int):
    try:
        game_statistics = models.GameStatisticsHistorical(
            game_id=game_id, current_ranking=1000000
        )
        db.add(game_statistics)
        db.commit()
        db.refresh(game_statistics)

    except SQLAlchemyError as e:
        db.rollback()
        if "Duplicate" not in str(e):
            logger.info("Error creating games statistics historical: " + str(e))
            raise e


def update_avg_time_game(db: Session, game_id: str, avg_time: int):
    logger.info("Updating avg time for game...")
    try:
        stmt = (
            update(models.Game)
            .where(models.Game.id == game_id)
            .values(
                avg_time=avg_time,
            )
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        logger.info(e)
        raise e


def update_game(db: Session, game_id: int, game: schemas.UpdateGame):
    try:
        db_game = get_game_by_id(db, game_id)
        name = game.name if game.name is not None else db_game.name
        dev = game.dev if game.dev is not None else db_game.dev
        steam_id = game.steam_id if game.steam_id is not None else db_game.steam_id
        image_url = game.image_url if game.image_url is not None else db_game.image_url
        release_date = (
            game.release_date if game.release_date is not None else db_game.release_date
        )
        genres = game.genres if game.genres is not None else db_game.genres
        avg_time = game.avg_time if game.avg_time is not None else db_game.avg_time
        stmt = (
            update(models.Game)
            .where(models.Game.id == game_id)
            .values(
                name=name,
                dev=dev,
                steam_id=steam_id,
                image_url=image_url,
                release_date=release_date,
                genres=genres,
                avg_time=avg_time,
            )
        )
        db.execute(stmt)
        db.commit()
        clockify_api.update_project_name(game_id, name)
        return db.query(models.Game).filter(models.Game.id == game_id).first()
    except Exception as e:
        db.rollback()
        error_message = "Error updating game: " + str(e)
        logger.info(error_message)
        raise RuntimeError(error_message) from e


def update_total_played_time(db: Session, game_id, total_played):
    try:
        game = get_game_by_id(db, game_id)
        stmt = (
            update(models.GameStatistics)
            .where(models.GameStatistics.game_id == game.id)
            .values(played_time=total_played)
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        logger.info(e)
        raise e


def get_most_played_time(db: Session, limit: int = None) -> list[models.GameStatistics]:
    if limit is not None:
        return (
            db.query(models.GameStatistics)
            .order_by(desc(models.GameStatistics.played_time))
            .limit(limit)
        )
    else:
        return db.query(models.GameStatistics).order_by(
            desc(models.GameStatistics.played_time)
        )


def current_ranking_hours(db: Session, limit: int = 11) -> list[models.GameStatistics]:
    try:
        return (
            db.query(models.GameStatistics)
            .order_by(asc(models.GameStatistics.current_ranking))
            .limit(limit)
        )
    except Exception as e:
        logger.info(e)


def update_current_ranking_hours(db: Session, i, game_id):
    try:
        stmt = (
            update(models.GameStatistics)
            .where(models.GameStatistics.game_id == game_id)
            .values(current_ranking=i)
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        logger.info(
            "Error updating current ranking for game " + str(game_id) + ". " + str(e)
        )

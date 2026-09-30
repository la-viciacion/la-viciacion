import datetime
import uuid
from typing import Union
import random

from sqlalchemy import asc, create_engine, delete, desc, func, select, text, true, update, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import models, schemas
from ..utils import actions
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

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


def genre_list(genres: str | list[str] | None) -> list[str]:
    """Genres as a clean list: `games.genres` is one comma separated string."""
    if genres is None:
        return []
    if isinstance(genres, str):
        genres = genres.split(",")
    return [g.strip() for g in genres if g and g.strip()]


def recommended_games(
    db: Session, user_id: int, genres: str | list[str] | None = None, limit: int = None
):
    """Games (of those genres, if any) that other players have and `user_id` has never played."""
    genres_filter = [models.Game.genres.ilike(f"%{genre}%") for genre in genre_list(genres)]
    played_by_user = select(models.UserGame.game_id).where(models.UserGame.user_id == user_id)
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
        .filter(models.UserGame.game_id.notin_(played_by_user))
        .filter(or_(*genres_filter) if genres_filter else true())
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
    logger.info(f"Adding new game to DB: {game.name} (rawg_id: {game.rawg_id})")

    # 1. Resolve official game data from RAWG first
    game_info = await utils.get_new_game_info(game)
    official_name = game_info.name if game_info.name else game.name

    # 2. Check if the game already exists in DB by rawg_id or official name
    existing_game = None
    if game_info.rawg_id:
        existing_game = db.query(models.Game).filter(models.Game.rawg_id == game_info.rawg_id).first()
    if not existing_game and official_name:
        existing_game = db.query(models.Game).filter(models.Game.name == official_name).first()
    if existing_game:
        logger.info(f"Game '{official_name}' already exists in DB (id: {existing_game.id})")
        return existing_game

    # 3. Generate a local id for the new game
    game_id = str(uuid.uuid4())

    # 4. Create and persist Game
    game_to_add = models.Game(
        id=game_id,
        name=official_name,
        dev=game_info.dev,
        steam_id=game_info.steam_id,
        image_url=game_info.image_url,
        release_date=game_info.release_date,
        genres=game_info.genres,
        avg_time=game_info.avg_time,
        slug=game_info.slug,
        rawg_id=game_info.rawg_id,
    )
    try:
        db.add(game_to_add)
        db.commit()
        db.refresh(game_to_add)
        game_added = game_to_add

        logger.info(f"Game '{official_name}' successfully added to DB with id {game_added.id}")
        return game_added
    except Exception as e:
        logger.error("Error adding new game: " + str(e))
        db.rollback()
        if "Duplicate" not in str(e):
            logger.warning("Error adding new game: " + str(e))
            raise e
        # If it was duplicate, return the existing game
        existing = db.query(models.Game).filter(models.Game.name == official_name).first()
        if existing:
            return existing
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
        return db.query(models.Game).filter(models.Game.id == game_id).first()
    except Exception as e:
        db.rollback()
        error_message = "Error updating game: " + str(e)
        logger.info(error_message)
        raise RuntimeError(error_message) from e



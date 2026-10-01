import datetime
import math
import uuid
from typing import Union
import random

from starlette.concurrency import run_in_threadpool
from sqlalchemy import asc, create_engine, delete, desc, func, select, text, true, update, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import models, schemas
from ..utils import actions
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
        .filter(models.UserGame.user_id != user_id, models.not_god(), models.User.is_active == 1)
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


def recommendation_candidates(db: Session, user_id: int) -> list[dict]:
    """Every game other (active) players have and `user_id` has never had in their library, any season.

    The ones more players share come first, then those more of them completed, then by name, so the
    answer is the same until somebody's library changes."""
    owned = select(models.UserGame.game_id).where(models.UserGame.user_id == user_id)
    player = func.coalesce(models.User.name, models.User.username)
    rows = (
        db.query(
            models.Game.id, models.Game.name, models.Game.genres, models.Game.image_url,
            models.User.id, player, models.UserGame.completed,
        )
        .select_from(models.UserGame)
        .join(models.Game, models.UserGame.game_id == models.Game.id)
        .join(models.User, models.UserGame.user_id == models.User.id)
        .filter(
            models.UserGame.user_id != user_id,
            models.UserGame.game_id.notin_(owned),
            models.User.is_active == 1,
            models.not_god(),
        )
        .all()
    )
    found: dict[str, dict] = {}
    completed_by: dict[str, set[int]] = {}
    for game_id, name, genres, image_url, owner_id, owner, completed in rows:
        item = found.setdefault(
            game_id,
            {"game_id": game_id, "game_name": name, "genres": genre_list(genres), "image_url": image_url, "players": []},
        )
        if owner not in item["players"]:
            item["players"].append(owner)
        if completed:
            completed_by.setdefault(game_id, set()).add(owner_id)
    # what the other players have put into each game: seconds and finished sessions, any season
    activity = {
        game_id: (seconds or 0, sessions)
        for game_id, seconds, sessions in db.query(
            models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds), func.count(models.GameTimer.id)
        )
        .join(models.User, models.GameTimer.user_id == models.User.id)
        .filter(
            models.GameTimer.game_id.in_(list(found)),
            models.GameTimer.is_active == False,  # noqa: E712
            models.GameTimer.user_id != user_id,
            models.User.is_active == 1,
            models.not_god(),
        )
        .group_by(models.GameTimer.game_id)
    } if found else {}
    for game_id, item in found.items():
        item["players"].sort(key=str.lower)
        item["completed_by"] = len(completed_by.get(game_id, ()))
        item["played_seconds"], item["sessions"] = activity.get(game_id, (0, 0))
    return sorted(found.values(), key=lambda i: (-len(i["players"]), -i["completed_by"], i["game_name"].lower()))


# How much each signal weighs in the chance of a candidate being picked. Hours and sessions go through
# a logarithm so a game somebody left running for months does not crowd out the rest.
W_PLAYER = 2.0  # per player that has it
W_COMPLETED = 3.0  # per player that completed it
W_HOURS = 1.5  # per ln(1 + hours played by everybody else)
W_SESSIONS = 1.0  # per ln(1 + sessions of everybody else)


def genre_affinity(db: Session, user_id: int) -> dict[str, float]:
    """The share of the user's playing time that went to each genre (a game with several genres counts
    for each of them, so the shares can add up to more than 1)."""
    rows = (
        db.query(models.Game.genres, func.sum(models.GameTimer.duration_seconds))
        .join(models.GameTimer, models.GameTimer.game_id == models.Game.id)
        .filter(models.GameTimer.user_id == user_id, models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.Game.id, models.Game.genres)
        .all()
    )
    total = sum(seconds or 0 for _, seconds in rows)
    shares: dict[str, float] = {}
    for genres, seconds in rows:
        for genre in genre_list(genres):
            shares[genre.lower()] = shares.get(genre.lower(), 0) + (seconds or 0) / total
    return shares if total else {}


def recommendation_weight(item: dict, affinity: dict[str, float]) -> float:
    """The chance (relative to the others) that a candidate is picked: what the others have put into it
    (players, completions, hours, sessions) times a boost, up to double, for the genres the user plays most."""
    base = (
        1
        + W_PLAYER * len(item["players"])
        + W_COMPLETED * item["completed_by"]
        + W_HOURS * math.log1p(item["played_seconds"] / 3600)
        + W_SESSIONS * math.log1p(item["sessions"])
    )
    liked = min(1.0, sum(affinity.get(genre.lower(), 0) for genre in item["genres"]))
    return base * (1 + liked)


def weighted_sample(weights: list[float], k: int, rng=random) -> list[int]:
    """Indices of `k` items picked without repeats, each with a chance proportional to its weight
    (Efraimidis-Spirakis: the k biggest of random() ** (1 / weight))."""
    keys = sorted(((rng.random() ** (1 / w), i) for i, w in enumerate(weights)), reverse=True)
    return sorted(i for _, i in keys[:k])


def recommendations_for(db: Session, user_id: int, limit: int = 12, rng=random) -> list[dict]:
    """`limit` games picked at random among the candidates, favouring the ones the others have shared,
    completed and played most and the genres this user plays most; every visit shows others. The picked
    ones keep the candidates' order."""
    candidates = recommendation_candidates(db, user_id)
    if not candidates:
        return []
    affinity = genre_affinity(db, user_id)
    chosen = weighted_sample([recommendation_weight(c, affinity) for c in candidates], limit, rng)
    return [candidates[i] for i in chosen]


async def new_game(db: Session, game: schemas.NewGame) -> models.Game:
    logger.info(f"Adding new game to DB: {game.name} (rawg_id: {game.rawg_id})")

    # 1. Resolve official game data from RAWG first (network: awaited, off the DB)
    game_info = await utils.get_new_game_info(game)
    # 2. everything else is database work: keep it off the event loop
    return await run_in_threadpool(_store_game, db, game, game_info)


def _store_game(db: Session, game: schemas.NewGame, game_info: schemas.NewGame) -> models.Game:
    official_name = game_info.name if game_info.name else game.name

    # Check if the game already exists in DB by rawg_id or official name
    existing_game = None
    if game_info.rawg_id:
        existing_game = db.query(models.Game).filter(models.Game.rawg_id == game_info.rawg_id).first()
    if not existing_game and official_name:
        existing_game = db.query(models.Game).filter(models.Game.name == official_name).first()
    if existing_game:
        logger.info(f"Game '{official_name}' already exists in DB (id: {existing_game.id})")
        return existing_game

    # Generate a local id for the new game
    game_id = str(uuid.uuid4())

    # Create and persist Game
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



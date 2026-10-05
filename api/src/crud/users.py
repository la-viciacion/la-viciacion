import datetime
import json
from typing import Union
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
from . import games, scores
from ..utils.logger import LogManager
from ..utils import seasons, streaks

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

#################
##### USERS #####
#################


GOD_USERNAME = models.GOD_USERNAME
GOD_NAME = "Dios"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _matches_password(password: str, stored: str | None) -> bool:
    try:
        return bool(stored) and bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:  # not a bcrypt hash
        return False


def ensure_god_user(db: Session):
    """
    Emergency administrator: make sure the "admin" user ("Dios") exists, is active,
    is admin and has the password defined in GOD_ADMIN_PASS. Runs on every API start,
    so restarting the API always restores access even if the account was altered.
    """
    if not config.GOD_ADMIN_PASS:
        raise ValueError("GOD_ADMIN_PASS must not be empty")
    try:
        db_user = (
            db.query(models.User).filter(models.User.username == GOD_USERNAME).first()
        )
        if db_user is None:
            db.add(
                models.User(
                    name=GOD_NAME,
                    username=GOD_USERNAME,
                    password=hash_password(config.GOD_ADMIN_PASS),
                    is_admin=1,
                    is_active=1,
                )
            )
            logger.info("God admin user created")
        else:
            db_user.name = GOD_NAME
            # a new hash on every start would change the token fingerprint (auth.password_fingerprint)
            # and log the admin out each time: only replace it when the password really differs
            if not _matches_password(config.GOD_ADMIN_PASS, db_user.password):
                db_user.password = hash_password(config.GOD_ADMIN_PASS)
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


def seasons_played(db: Session, user_id: int) -> list[int]:
    """The seasons the user has something in (plus the running one), newest first."""
    found = {seasons.current()}
    for model in (models.UserGame, models.GameTimer, models.UserAchievement):
        found.update(year for (year,) in db.query(model.season).filter(model.user_id == user_id).distinct() if year)
    return sorted(found, reverse=True)


def get_profile(db: Session, user: models.User, season: int = None) -> dict:
    """Main stats of a user for the profile page. `season` may be seasons.ALL for the totals."""
    season = seasons.or_current(season)
    every = season == seasons.ALL
    from . import time_entries as time_entries_crud

    played_days = time_entries_crud.get_played_days(db, user.id, season=season)
    best_date, best_streak, current_streak = streaks.streak_summary(
        played_days, datetime.date.today(), seasons.current() if every else season
    )[:3]
    total = time_entries_crud.get_user_played_time(db, user.id, season)
    played_time = total[1] if total is not None else 0
    achievements = get_achievements(db, user.username, season)
    ratings = scores.user_scores(db, user.id)
    return {
        "season": "all" if every else season,
        "seasons": seasons_played(db, user.id),
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "telegram_id": user.telegram_id,
        },
        "stats": {
            "played_time": int(played_time or 0),
            "played_days": len(played_days),
            "played_games": count_played_games(db, user.id, season),
            "completed_games": count_completed_games(db, user.id, season),
            "current_streak": current_streak,
            "best_streak": best_streak,
            "achievements": len(achievements),
        },
        "top_games": [
            {"game_id": r.game_id, "game_name": r.game_name, "played_time": r.played_time or 0, "score": ratings.get(r.game_id)}
            for r in top_games(db, user.username, limit=5, season=season)
        ],
        "achievements": [
            {"id": r.achievement_id, "title": r.title, "date": r.date} for r in achievements[-5:][::-1]
        ],
    }


def get_users(db: Session, is_active: bool = True) -> list[models.User]:
    """
    Get the players based on their active status (never the emergency account).

    Args:
        db (Session): DB Session
        is_active (bool | None): Filter by active status.
                                 True for active, False for inactive, None for all.

    Returns:
        list[models.User]: List of users based on the filter.
    """
    try:
        query = db.query(models.User).filter(models.not_god())
        if is_active is True:  # Apply filter only if is_active is not None
            query = query.filter(models.User.is_active == is_active)
        return query.all()
    except SQLAlchemyError as e:
        logger.error("Error getting users: " + str(e))
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


def ensure_library_entry(
    db: Session, user_id: int, game_id: str, platform: str | None, when: datetime.date | datetime.datetime
) -> bool:
    """Make sure the user has a library entry for (game, platform, season of `when`).
    Adds it (not committed, no announcement) if missing; returns whether it did."""
    day = when.date() if isinstance(when, datetime.datetime) else when
    exists = (
        db.query(models.UserGame)
        .filter_by(user_id=user_id, game_id=game_id, platform=platform, season=seasons.of(day))
        .first()
    )
    if exists is not None:
        return False
    db.add(models.UserGame(user_id=user_id, game_id=game_id, platform=platform, completed=0, started_date=day))
    return True


def drop_empty_entry(db: Session, user_id: int, game_id: str, platform: str | None, season: int) -> bool:
    """Delete the library entry (game, platform, season) if nothing is left in it: no session
    (the caller flushed its change first) and no completion. Not committed."""
    entry = (
        db.query(models.UserGame)
        .filter_by(user_id=user_id, game_id=game_id, platform=platform, season=season)
        .first()
    )
    if entry is None or entry.completed:
        return False
    has_sessions = (
        db.query(models.GameTimer.id)
        .filter_by(user_id=user_id, game_id=game_id, platform=platform, season=season)
        .first()
        is not None
    )
    if has_sessions:
        return False
    db.delete(entry)
    return True


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
            # messages and rankings print the name, so it is never empty
            name=(name or "").strip() or username,
            email=email,
            password=hashed,
            is_admin=int(is_admin),
            is_active=int(is_active),
            telegram_id=telegram_id,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error inserting user: " + str(e))
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


async def announce_new_game(
    db: Session, user: models.User, game_db: models.Game, started_date, silent: bool
) -> None:
    """Tell the group a user started a game. The entry is already saved: a failure here is only logged."""
    try:
        # the season of the new entry, not the running one: a backdated start belongs to its own season
        played_games = count_played_games(db, user.id, seasons.of(started_date))
        started_game = utils.escape_markdown(game_db.name)
        if game_db.slug:
            started_game = "[" + started_game + "](https://rawg.io/games/" + game_db.slug + ")"
        msg = (
            "*"
            + utils.escape_markdown(user.name)
            + "* acaba de empezar "
            + started_game
            + ", su juego número "
            + str(played_games)
            + " de este año."
        )
        await utils.send_message(
            msg,
            silent,
            ai_use="new_game",
        )
    except Exception as e:
        logger.error("Error announcing new game: " + str(e))


def add_new_game(
    db: Session,
    game: schemas.NewGameUser,
    user: models.User,
    start_date: str = None,
) -> models.UserGame:
    """Add a library entry for the game. Announcing it is a separate, slow step (announce_new_game)."""
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
        logger.info("Game added!")
        return user_game
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error adding new game user: " + str(e))
        raise


def count_played_games(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    try:
        query = db.query(func.count(func.distinct(models.UserGame.game_id))).filter(models.UserGame.user_id == user_id)
        if season != seasons.ALL:
            query = query.filter(models.UserGame.season == season)
        return query.scalar()
    except SQLAlchemyError as e:
        logger.error("Error counting played games: " + str(e))
        raise e


def count_completed_games(db: Session, user_id: int, season: int = None):
    season = seasons.or_current(season)
    try:
        query = db.query(models.UserGame).filter_by(user_id=user_id, completed=1)
        if season != seasons.ALL:
            query = query.filter_by(season=season)
        return query.count()
    except SQLAlchemyError as e:
        logger.error("Error counting completed games: " + str(e))
        raise e


def played_game_dates(db: Session, user_id: int, season: int = None) -> list[datetime.date]:
    """The day the user first played each distinct game of the season, oldest first: the Nth one is
    the day their Nth game began."""
    season = seasons.or_current(season)
    query = db.query(func.min(models.UserGame.started_date)).filter(models.UserGame.user_id == user_id)
    if season != seasons.ALL:
        query = query.filter(models.UserGame.season == season)
    return sorted(day for (day,) in query.group_by(models.UserGame.game_id).all())


def completed_game_dates(db: Session, user_id: int, season: int = None) -> list[datetime.date]:
    """The day of each completion of the season, oldest first (one per completed library entry, as
    count_completed_games counts them)."""
    season = seasons.or_current(season)
    when = func.coalesce(models.UserGame.completed_date, models.UserGame.started_date)
    query = db.query(when).filter(models.UserGame.user_id == user_id, models.UserGame.completed == 1)
    if season != seasons.ALL:
        query = query.filter(models.UserGame.season == season)
    return sorted(day for (day,) in query.all())


def first_entry_per_game(rows, limit: int | None = None) -> list:
    """The first row of each game, in the order given, at most `limit` of them."""
    seen, unique = set(), []
    for row in rows:
        if row["game_id"] in seen:
            continue
        seen.add(row["game_id"])
        unique.append(row)
        if limit is not None and len(unique) == limit:
            break
    return unique


def get_games(
    db: Session,
    user_id,
    limit=None,
    completed=None,
    season: int = None,
) -> list[schemas.UserGame]:
    """One row per game the user has in the library of the season, most recently played first.

    A game on two platforms counts once (its most recently played entry)."""
    season = seasons.or_current(season)
    # Local import to avoid a circular import (crud.time_entries imports crud.users).
    from . import time_entries as time_entries_crud

    entry_time = time_entries_crud.entry_played_time(user_id)
    last = _last_played_by_year(user_id)
    stmt = (
        select(
            models.UserGame.__table__,
            func.coalesce(entry_time.c.played_time, 0).label("played_time"),
            models.UserGame.platform.label("platform_id"),
            models.Game.name.label("game_name"),
            models.PlatformTag.name.label("platform_name"),
            last.c.last_played.label("last_played_time"),
        )
        .join(models.Game, models.UserGame.game_id == models.Game.id)
        .outerjoin(models.PlatformTag, models.UserGame.platform == models.PlatformTag.id)
        .outerjoin(
            last,
            and_(
                last.c.user_id == models.UserGame.user_id,
                last.c.game_id == models.UserGame.game_id,
                last.c.season == models.UserGame.season,
            ),
        )
        .outerjoin(
            entry_time,
            and_(
                entry_time.c.user_id == models.UserGame.user_id,
                entry_time.c.game_id == models.UserGame.game_id,
                entry_time.c.season == models.UserGame.season,
            ),
        )
        .where(models.UserGame.user_id == user_id, models.UserGame.season == season)
        .order_by(
            last.c.last_played.is_(None),
            last.c.last_played.desc(),
            models.UserGame.started_date.desc(),
            models.UserGame.id.desc(),
        )
    )
    if completed is not None:
        stmt = stmt.where(func.coalesce(models.UserGame.completed, 0) == (1 if completed else 0))
    # a user has tens of entries per season: deduplicate here, after the ordering, so `limit`
    # counts games and not rows
    return first_entry_per_game(db.execute(stmt).mappings().all(), limit)


def get_game_by_id(db: Session, user_id, game_id, season) -> models.UserGame:
    return (
        db.query(models.UserGame)
        .filter_by(user_id=user_id, game_id=game_id, season=season)
        .first()
    )


# ── Library: every game of a user, with its completion state ──


def _last_played_by_year(user_id: int | None = None):
    """Latest session start per (user, game, season), of one user when given (see entry_played_time)."""
    stmt = select(
        models.GameTimer.user_id.label("user_id"),
        models.GameTimer.game_id.label("game_id"),
        models.GameTimer.season.label("season"),
        func.max(models.GameTimer.start_time).label("last_played"),
    )
    if user_id is not None:
        stmt = stmt.where(models.GameTimer.user_id == user_id)
    return stmt.group_by(models.GameTimer.user_id, models.GameTimer.game_id, models.GameTimer.season).subquery("last_played")


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


def _library_query(user_id: int, entry_id: int | None = None, game_id: str | None = None):
    from . import time_entries as time_entries_crud

    last = _last_played_by_year(user_id)
    entry_time = time_entries_crud.entry_played_time(user_id)
    stmt = (
        select(
            models.UserGame,
            func.coalesce(entry_time.c.played_time, 0).label("played_time"),
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
        .outerjoin(
            entry_time,
            and_(
                entry_time.c.user_id == models.UserGame.user_id,
                entry_time.c.game_id == models.UserGame.game_id,
                entry_time.c.season == models.UserGame.season,
            ),
        )
        .where(models.UserGame.user_id == user_id)
    )
    if entry_id is not None:
        stmt = stmt.where(models.UserGame.id == entry_id)
    if game_id is not None:
        stmt = stmt.where(models.UserGame.game_id == game_id)
    # most recently played first; entries without sessions go last (by start date)
    return stmt.order_by(
        last.c.last_played.is_(None),
        last.c.last_played.desc(),
        models.UserGame.started_date.desc(),
        models.UserGame.id.desc(),
    )


def is_abandoned(entry: models.UserGame, last_played: datetime.datetime | None) -> bool:
    """An entry is abandoned from the moment the player says so until they play it again: a session after
    that moment resumes it, so adding sessions needs no bookkeeping. A completed entry is never abandoned."""
    if entry.completed or entry.abandoned_at is None:
        return False
    return last_played is None or last_played <= entry.abandoned_at


def _library_item(row, completed_keys: set, current_season: int, ratings: dict) -> dict:
    entry = row.UserGame
    done = bool(entry.completed)
    abandoned = is_abandoned(entry, row.last_played)
    # why the completion of the entry cannot be touched (None when it can): a closed season is
    # frozen, completed or not; a pending entry is also blocked by another platform's completion
    blocked = None
    if entry.season != current_season:
        blocked = "closed_season"
    elif not done and (entry.game_id, entry.season) in completed_keys:
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
        "played_time": row.played_time or 0,
        "completed": done,
        "completed_date": entry.completed_date,
        "score": ratings.get(entry.game_id),  # 1-100 or None: per game, the same on every entry of it
        # a game can be completed once per season, and only in the running one
        "can_complete": not done and blocked is None,
        "complete_blocked": blocked,  # "closed_season" | "completed_in_season" | None
        "abandoned": abandoned,
        # giving a game up (and taking it back) is, like completing, only for the running season
        "can_abandon": not done and not abandoned and entry.season == current_season,
        "can_resume": abandoned and entry.season == current_season,
    }


def get_library(
    db: Session, user_id: int, limit: int = 15, offset: int = 0, game_id: str | None = None, only_season: int | None = None
) -> dict:
    """`season` in the answer is the running one (it decides what can be completed), not the filter."""
    season = seasons.current()
    count = db.query(models.UserGame).filter(models.UserGame.user_id == user_id)
    if game_id is not None:
        count = count.filter(models.UserGame.game_id == game_id)
    query = _library_query(user_id, game_id=game_id)
    if only_season is not None:
        count = count.filter(models.UserGame.season == only_season)
        query = query.where(models.UserGame.season == only_season)
    rows = db.execute(query.limit(limit).offset(offset)).all()
    total = count.count()
    keys = _completed_keys(db, user_id)
    ratings = scores.user_scores(db, user_id)
    return {
        "season": season,
        "total": total,
        "items": [_library_item(r, keys, season, ratings) for r in rows],
    }


def get_library_item(db: Session, user_id: int, entry_id: int) -> dict | None:
    row = db.execute(_library_query(user_id, entry_id)).first()
    if row is None:
        return None
    return _library_item(row, _completed_keys(db, user_id), seasons.current(), scores.user_scores(db, user_id))


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


def set_abandoned(db: Session, entry: models.UserGame, abandoned: bool, now: datetime.datetime):
    """Mark the entry as abandoned as of `now`, or take the mark back."""
    try:
        entry.abandoned_at = now if abandoned else None
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error changing the abandoned mark: " + str(e))
        raise


def set_completed_date(db: Session, entry: models.UserGame, completed_date: datetime.date):
    try:
        entry.completed_date = completed_date
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error changing completion date: " + str(e))
        raise


def complete_entry(
    db: Session,
    entry: models.UserGame,
    completed_date: datetime.date | None = None,
) -> models.UserGame:
    """Mark one library entry as completed. The follow-ups (average time, achievements,
    group announcement) are slow and best effort: see after_completion, run in the background."""
    try:
        entry.completed = 1
        entry.completed_date = completed_date or datetime.date.today()
        entry.abandoned_at = None  # finished after all
        db.commit()
        logger.info("Game completed")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Error completing game: " + str(e))
        raise
    return entry


async def after_completion(db: Session, entry: models.UserGame, silent: bool):
    game = games.get_game_by_id(db, entry.game_id)
    user = get_user_by_id(db, entry.user_id)
    game_info = await utils.get_game_info(game.name)
    hltb = game_info["hltb"]
    # a failed lookup must not wipe the time the game already has
    avg_time = (hltb["comp_main"] if hltb is not None else 0) or game.avg_time or 0
    if avg_time != game.avg_time:
        games.update_avg_time_game(db, entry.game_id, avg_time)
        game = games.get_game_by_id(db, entry.game_id)
    from . import time_entries as time_entries_crud

    completion_time = sum(
        seconds or 0
        for _, seconds in time_entries_crud.get_user_games_played_time(db, entry.user_id, entry.game_id, entry.season)
    )

    # Local import to avoid a circular import (crud.achievements imports crud.users).
    from .achievements import Achievements

    achievements = Achievements()
    await achievements.just_in_time(
        db, user, completion_time, avg_time, entry.game_id, silent=silent
    )
    await achievements.user_completed_total_games(db, user, silent=silent)

    message = (
        user.name
        + " acaba de completar su juego número "
        + str(count_completed_games(db, user.id, entry.season))
        + ": *"
        + game.name
        + "* en "
        + str(utils.format_duration(completion_time))
        + ". La media está en "
        + str(utils.format_duration(avg_time))
        + "."
    )
    logger.info(message)
    new_game_info = None
    suggestions = games.recommended_games(db, entry.user_id, genres=game.genres)
    if suggestions:
        new_game = random.choice(suggestions)
        new_game_info = {"game": new_game[2], "user": new_game[4]}
    await utils.send_message(
        message,
        silent,
        ai_use="completed_game",
        new_game_recommended=new_game_info,
    )


def get_streaks(db: Session, username: str):
    """Current and best streak of the running season, computed from the sessions."""
    from . import time_entries as time_entries_crud

    try:
        user = get_user_by_username(db, username)
        season = seasons.current()
        days = time_entries_crud.get_played_days(db, user.id, season=season)
        best_date, best, current = streaks.streak_summary(days, datetime.date.today(), season)[:3]
        return [{"current_streak": current, "best_streak": best, "best_streak_date": best_date}]
    except Exception as e:
        logger.error(e)
        raise e


######################
##### STATISTICS #####
######################


def top_games(db: Session, username: str, limit: int = 10, season: int = None):
    from . import time_entries as time_entries_crud

    season = seasons.or_current(season)
    try:
        user = get_user_by_username(db, username)
        if season == seasons.ALL:
            # across seasons a game is one row: its time in every season added up
            sessions = time_entries_crud.sessions_subquery()
            total = func.sum(sessions.c.duration)
            stmt = (
                select(sessions.c.game_id, models.Game.name.label("game_name"), total.label("played_time"))
                .join(models.Game, models.Game.id == sessions.c.game_id)
                .where(sessions.c.user_id == user.id)
                .group_by(sessions.c.game_id, models.Game.name)
                .order_by(desc(total))
                .limit(limit)
            )
            return db.execute(stmt).fetchall()
        entry_time = time_entries_crud.entry_played_time(user.id)
        played = func.coalesce(entry_time.c.played_time, 0)
        stmt = (
            select(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name.label("game_name"),
                played.label("played_time"),
            )
            .join(models.User, models.User.id == models.UserGame.user_id)
            .join(models.Game, models.Game.id == models.UserGame.game_id)
            .outerjoin(
                entry_time,
                and_(
                    entry_time.c.user_id == models.UserGame.user_id,
                    entry_time.c.game_id == models.UserGame.game_id,
                    entry_time.c.season == models.UserGame.season,
                ),
            )
            .where(
                models.UserGame.user_id == user.id,
                models.UserGame.season == season,
            )
            .group_by(
                models.UserGame.user_id,
                models.UserGame.game_id,
                models.Game.name,
                entry_time.c.played_time,
            )
            .order_by(desc(played))
            .limit(limit)
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.error(e)
        raise e


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
                True if season == seasons.ALL else models.UserAchievement.season == season,
            )
            .group_by(
                models.UserAchievement.user_id,
                models.UserAchievement.achievement_id,
                models.Achievement.id,
            )
            .order_by(asc(models.UserAchievement.date), asc(models.UserAchievement.id))
        )
        return db.execute(stmt).fetchall()
    except Exception as e:
        logger.info(e)
        raise e

import asyncio
import datetime
import json
import re
import threading
import time
from typing import Union

import requests
from sqlalchemy import asc, create_engine, desc, func, select, text, update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import games, rankings, time_entries, users
from ..crud.achievements import Achievements
from ..database import models, schemas
from . import my_utils as utils
from . import push
from ..utils import ai_prompts as prompts
from ..utils import seasons, streaks
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()
achievements = Achievements()


##############################
##### ACHIEVEMENT CHECKS #####
##############################
# Nothing about rankings, totals or streaks is stored: they are computed from the
# sessions whenever they are needed (crud/rankings.py). What is stored is only what
# cannot be derived: the achievements a player has unlocked.


async def check_user(
    db: Session,
    user: models.User,
    silent: bool = False,
    announce_streak_loss: bool = False,
):
    """Check every achievement of one user against their sessions and library."""
    current_season = seasons.current()
    today = datetime.date.today()

    played_days = time_entries.get_played_days(db, user.id)[1]
    await achievements.user_played_total_days(db, user, played_days, silent=silent)
    best_streak_date, best_streak = streaks.streak_summary(played_days, today, current_season)[:2]
    if announce_streak_loss:
        await announce_lost_streak(user, played_days, today, silent)
    for game_id, played_time in time_entries.get_user_games_played_time(db, user.id):
        if played_time is not None:
            await achievements.user_played_hours_game(
                db=db, user=user, game_id=game_id, played_time=played_time, silent=silent
            )
    played_time = time_entries.get_user_played_time(db, user.id)
    played_time = played_time[1] if played_time is not None else 0
    await achievements.user_played_total_time(db, user, played_time, silent=silent)
    await achievements.user_session_time(db, user, silent=silent)
    await achievements.user_played_total_games(db, user, silent=silent)
    await achievements.user_completed_total_games(db, user, silent=silent)
    await achievements.user_streak(db, user, best_streak, best_streak_date, silent=silent)
    await achievements.user_played_day_time(db, user, silent)
    await achievements.user_played_hours_game_day(db, user, silent=silent)
    await achievements.user_played_games_per_day(db, user, silent=silent)
    await achievements.happy_new_year(db, user, silent)
    await achievements.early_riser(db, user, silent)
    await achievements.nocturnal(db, user, silent)


async def check_users(
    db: Session,
    silent: bool = False,
    only_active_users: bool = True,
    user_ids: list[int] | None = None,
    announce_streak_loss: bool = False,
):
    """Check the achievements of every user (or of `user_ids`).

    Event-driven: it runs right after a timer stops (routers/timers.py), from the
    admin panel, and from the scheduler (utils/scheduler.py) for the daily check.
    """
    start_time = time.time()
    achievements.populate_achievements(db)
    users_db = users.get_users(db, only_active_users)
    if user_ids is not None:
        users_db = [u for u in users_db if u.id in user_ids]
    try:
        for user in users_db:
            await check_user(db, user, silent=silent, announce_streak_loss=announce_streak_loss)
        await achievements.teamwork(db, silent)
        elapsed_time = time.time() - start_time
        if elapsed_time > 30:
            await utils.send_message_to_admins(
                db, "❗Ejecución lenta❗\nLa última comprobación ha durado más de 30 segundos"
            )
        logger.info("Elapsed time: " + str(elapsed_time))
    except Exception as e:
        logger.error("Error checking achievements: " + str(e))
        await utils.send_message_to_admins(db, "Error checking achievements: " + str(e))


# Serializes the checks that follow a session: two people stopping timers at once must
# not run the same checks concurrently (duplicate achievements/notifications).
_check_lock = threading.Lock()


def after_session_change(
    user_id: int | None = None,
    silent: bool = False,
    ranking_before: dict | None = None,
):
    """Background-task entrypoint for routers/timers.py and the admin panel.

    Deliberately a plain `def`: Starlette runs it in a worker thread. The checks are a
    long chain of blocking DB/OpenAI calls wrapped in async functions, so running them
    on the event loop would freeze every other request until they finished. It gets its
    own DB session (the request-scoped one is already closed by the time a
    BackgroundTask runs) and its own event loop.

    `ranking_before` is the snapshot taken before the change (see ranking_snapshot); when
    given and not silent, the ranking changes it caused are announced.
    """
    from ..database.database import SessionLocal

    async def _run():
        db = SessionLocal()
        try:
            await check_users(db, silent=silent, user_ids=None if user_id is None else [user_id])
            if ranking_before is not None:
                await announce_ranking_changes(db, ranking_before, silent)
        finally:
            db.close()

    with _check_lock:
        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error("Error checking after a session change: " + str(e))


async def announce_lost_streak(user: models.User, played_dates: list[datetime.date], today: datetime.date, silent: bool):
    """Announce a streak of more than 10 days on the day it is lost (daily check)."""
    lost = streaks.lost_streak(played_dates, today)
    if lost is not None:
        msg = user.name + " acaba de perder la racha de " + str(lost) + " días."
        logger.info(msg)
        await utils.send_message(msg, silent)


####################
##### RANKINGS #####
####################
# Announcements compare the ranking before and after a change: nothing is remembered
# between runs, so there is no stored position that could go out of date.


def push_has_devices(user_id: int) -> bool:
    """Does the user have a device subscribed to push notifications?"""
    from ..database.database import SessionLocal

    if not push.is_ready():
        return False
    with SessionLocal() as db:
        return db.query(models.PushSubscription.id).filter_by(user_id=user_id).first() is not None


def ranking_snapshot(db: Session) -> dict:
    """Order of the players (by hours) and of the games (by hours) right now."""
    return {
        "players": [row["user_id"] for row in rankings.user_hours_players(db)],
        "games": [row["game_id"] for row in time_entries.games_played_time(db)],
    }


def position_change(previous: int, current: int) -> tuple[int, str]:
    """(places climbed, arrow text) of an item that was at `previous` and is now at `current`."""
    climbed = previous - current
    if climbed > 0:
        return climbed, f"↑{climbed}"
    if climbed < 0:
        return climbed, f"↓{-climbed}"
    return 0, "="


def decorate_name(name: str, climbed: int) -> str:
    """Bold and emoji for a name according to how far it moved."""
    if climbed != 0:
        name = "*" + name + "*"
    if climbed > 1:
        return "🔥 " + name
    if climbed == 1:
        return "⬆️ " + name
    if climbed < -1:
        return "🔻 " + name
    if climbed == -1:
        return "⬇️ " + name
    return name


def _previous_positions(before_ids: list) -> dict:
    return {item: position for position, item in enumerate(before_ids, start=1)}


def order_changed(before_ids: list, after_ids: list) -> bool:
    """Did the relative order of the items present in both lists change?"""
    common = set(before_ids) & set(after_ids)
    return [i for i in before_ids if i in common] != [i for i in after_ids if i in common]


def players_ranking_message(before_ids: list, players: list[dict]) -> str | None:
    """Message for the players ranking, or None if the order did not change."""
    after_ids = [p["user_id"] for p in players]
    if not order_changed(before_ids, after_ids):
        return None
    previous = _previous_positions(before_ids)
    msg = "📣 Actualización del ránking de horas 📣\n"
    for position, player in enumerate(players, start=1):
        climbed, arrow = position_change(previous.get(player["user_id"], position), position)
        name = decorate_name(str(player["name"]), climbed)
        hours = utils.convert_time_to_hours(player["played_time"] or 0)
        msg += f"{position}. {name}: {hours} ({arrow})\n"
    return msg


def games_ranking_message(before_ids: list, games_now: list[dict]) -> str | None:
    """Message for the top 10 of games, or None if the top 10 did not change."""
    top = games_now[:10]
    if [g["game_id"] for g in top] == before_ids[:10]:
        return None
    previous = _previous_positions(before_ids)
    msg = "📣 Actualización del ránking de juegos 📣\n"
    for position, game in enumerate(top, start=1):
        climbed, arrow = position_change(previous.get(game["game_id"], position), position)
        name = decorate_name(str(game["name"]), climbed)
        msg += f"{position}. {name}: {utils.convert_time_to_hours(game['played_time'])} ({arrow})\n"
    # a game that was in the top 10 and is now 11th has fallen out of it
    if len(games_now) > 10 and previous.get(games_now[10]["game_id"], 11) < 11:
        dropped = games_now[10]
        msg += "----------\n"
        msg += f"11. {dropped['name']}: {utils.convert_time_to_hours(dropped['played_time'])} (💀)\n"
    return msg


async def announce_ranking_changes(db: Session, before: dict, silent: bool):
    """Announce how the players and games rankings moved since `before` (a ranking_snapshot)."""
    if silent:
        return
    try:
        message = games_ranking_message(before["games"], time_entries.games_played_time(db))
        if message:
            logger.info(message)
            await utils.send_message(message, silent, openai=True, system_prompt=prompts.RANKING_GAMES_PROMPT)
        message = players_ranking_message(before["players"], rankings.user_hours_players(db))
        if message:
            logger.info(message)
            await utils.send_message(message, silent, openai=True, system_prompt=prompts.RANKING_USER_PROMPT)
    except Exception as e:
        logger.error("Error announcing ranking changes: " + str(e))


##################
##### OTHERS #####
##################


async def check_forgotten_timer(db: Session, user: models.User):
    """Remind a user about a timer running for too long (the scheduler calls this hourly)."""
    if user.telegram_id is None and not push_has_devices(user.id):
        return
    forgotten_timer = time_entries.get_forgotten_game_timers(db, user_id=user.id)
    if forgotten_timer:
        logger.info(user.name + " has an active timer for more than 4 hours")
        msg = (
            "Hola, "
            + user.name
            + ". Tienes un timer activo desde hace más de 4 horas."
            + " Si es correcto, sigue disfrutando. Si te has olvidado de pararlo,"
            + " párala y edita la sesión con el tiempo correcto."
        )
        await utils.send_message_to_user(user.telegram_id, msg, user_id=user.id)


async def weekly_resume(
    db: Session, user: models.User, weeks_ago: int = 0, silent: bool = False
):
    """_summary_

    Args:
        db (Session): _description_
        user (models.User): _description_
        mode (int, optional): 0 = last week. 1 = current week. Defaults to 0.
        silent (bool, optional): _description_. Defaults to False.

    Returns:
        _type_: _description_
    """
    try:
        logger.info("Check weekly resume for " + user.name + "...")
        resume = {}
        # Last week
        user_weekly_resume = time_entries.get_weekly_resume(
            db, user, weeks_ago=weeks_ago
        )
        weekly_hours = user_weekly_resume[0][0]
        weekly_sessions = str(user_weekly_resume[0][1])
        weekly_games = str(user_weekly_resume[0][2])
        weekly_achievements = achievements.get_weekly_achievements(
            db, user, weeks_ago=weeks_ago
        )
        weekly_achievements = str(weekly_achievements[0][0])
        # Before last week
        user_last_weekly_resume = time_entries.get_weekly_resume(
            db, user, weeks_ago=weeks_ago + 1
        )
        last_weekly_hours = user_last_weekly_resume[0][0]
        last_weekly_sessions = str(user_last_weekly_resume[0][1])
        last_weekly_games = str(user_last_weekly_resume[0][2])
        last_weekly_achievements = achievements.get_weekly_achievements(
            db, user, weeks_ago=weeks_ago + 1
        )
        last_weekly_achievements = str(last_weekly_achievements[0][0])
        logger.info("Weekly resume hours:")
        logger.info("This week: " + str(weekly_hours))
        logger.info("Last week: " + str(last_weekly_hours))
        if weekly_hours is None:
            weekly_hours = 0
        if last_weekly_hours is None:
            last_weekly_hours = 0
        hours_diff = int(weekly_hours) - int(last_weekly_hours)
        hours_diff_str = ""
        if hours_diff >= 0:
            hours_diff_str = "+"
        logger.info("Weekly resume sessions:")
        logger.info("This week: " + str(weekly_sessions))
        logger.info("Last week: " + str(last_weekly_sessions))
        sessions_diff = int(weekly_sessions) - int(last_weekly_sessions)
        if sessions_diff > 0:
            sessions_diff = "+" + str(sessions_diff)
        logger.info("Weekly resume games:")
        logger.info("This week: " + str(weekly_games))
        logger.info("Last week: " + str(last_weekly_games))
        games_diff = int(weekly_games) - int(last_weekly_games)
        if games_diff > 0:
            games_diff = "+" + str(games_diff)
        logger.info("Weekly resume achievements:")
        logger.info("This week: " + str(weekly_achievements))
        logger.info("Last week: " + str(last_weekly_achievements))
        achievements_diff = int(weekly_achievements) - int(last_weekly_achievements)
        if achievements_diff > 0:
            achievements_diff = "+" + str(achievements_diff)
        msg = (
            "🤖*Aquí está tu resumen semanal*********🤖\n"
            + "Horas: "
            + utils.convert_time_to_hours(weekly_hours)
            + " ("
            + hours_diff_str
            + str(utils.convert_time_to_hours(hours_diff))
            + ") \n"
            + "Sesiones: "
            + weekly_sessions
            + " ("
            + str(sessions_diff)
            + ") \n"
            + "Juegos: "
            + weekly_games
            + " ("
            + str(games_diff)
            + ") \n"
            + "Logros: "
            + weekly_achievements
            + " ("
            + str(achievements_diff)
            + ") \n"
        )

        # logger.debug(msg)
        if not silent:
            await utils.send_message_to_user(user.telegram_id, msg, user_id=user.id)
        resume["hours"] = weekly_hours
        resume["sessions"] = weekly_sessions
        resume["games"] = weekly_games
        resume["achievements"] = weekly_achievements
        return resume
    except Exception as e:
        logger.error("Error sending weekly resume to user " + user.name + ": " + str(e))

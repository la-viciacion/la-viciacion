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
from ..crud import challenges as challenges_crud
from ..crud import games, rankings, time_entries, users, wishlist
from ..crud.achievements import Achievements, Played
from ..database import models, schemas
from . import challenges, my_utils as utils
from . import push, rawg_sync
from ..utils import seasons, streaks, user_settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

# Off: for now the wishlist releases are announced only to the group, the day before (announce_wishlist_eve).
# The private notice of the release day (check_wishlist, wishlist_release_message) stays: turning this on brings it back.
WISHLIST_PRIVATE_NOTICE = False

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
    checks: Achievements | None = None,
):
    """Check every achievement of one user against their sessions and library. `checks` is the set
    of checks to run (default: the running season's, storing and announcing what it finds)."""
    checks = checks or achievements
    played_days = time_entries.get_played_days(db, user.id, season=checks.season)
    await checks.user_played_total_days(db, user, played_days, silent=silent)
    await checks.user_played_hours_game(db, user, silent=silent)
    await checks.user_played_total_time(db, user, silent=silent)
    await checks.user_session_time(db, user, silent=silent)
    await checks.user_played_total_games(db, user, silent=silent)
    await checks.user_completed_total_games(db, user, silent=silent)
    await checks.user_streak(db, user, played_days, silent=silent)
    await checks.user_played_day_time(db, user, silent)
    await checks.user_played_hours_game_day(db, user, silent=silent)
    await checks.user_played_games_per_day(db, user, silent=silent)
    await checks.happy_new_year(db, user, silent)
    await checks.early_riser(db, user, silent)
    await checks.nocturnal(db, user, silent)
    await checks.completed_in_a_day(db, user, silent)
    await checks.rescued_games(db, user, silent)
    await checks.prodigal_son(db, user, played_days, silent)
    await checks.work_week(db, user, silent)
    await checks.saved_by_the_bell(db, user, silent)
    await checks.release_day(db, user, silent)


async def check_user_lifetime(
    db: Session,
    user: models.User,
    silent: bool = False,
    collected: list | None = None,
    undecided: set | None = None,
):
    """The achievements with no season limit (their key ends in _LIFETIME): worked out over the history from the
    season each begins to count from. With `collected` (a list) it only notes what the user deserves, and in
    `undecided` the keys that could not be told (the weather service was down). It costs nothing while none of
    them is switched on and valid."""
    base = achievements if collected is None else Achievements(silent=True, collected=collected, undecided=undecided)
    for view in base.lifetime_views(db):
        days = time_entries.get_played_days(db, user.id, season=seasons.ALL, since=view.since)
        await view.user_played_total_days(db, user, days, silent=silent)
        await view.user_played_hours_game(db, user, silent=silent)
        await view.user_played_total_time(db, user, silent=silent)
        await view.user_played_total_games(db, user, silent=silent)
        await view.user_completed_total_games(db, user, silent=silent)
        await view.external_days(db, user, silent=silent)
        await view.weather(db, user, silent=silent)
        await view.archaeologist(db, user, silent=silent)
        await view.birth_year_game(db, user, silent=silent)


async def check_users(
    db: Session,
    silent: bool = False,
    only_active_users: bool = True,
    user_ids: list[int] | None = None,
):
    """Check the achievements of every user (or of `user_ids`).

    Event-driven: it runs after a timer stops or a session or library entry changes (routers/timers.py,
    routers/manage.py, the import). Teamwork is not checked here: only a timer that starts can make it
    true (after_timer_start).
    """
    start_time = time.time()
    users_db = users.get_users(db, only_active_users)
    if user_ids is not None:
        users_db = [u for u in users_db if u.id in user_ids]
    failures: list[str] = []
    try:
        for user in users_db:
            # one user's failure must not skip the checks of the rest
            try:
                await check_user(db, user, silent=silent)
                await check_user_lifetime(db, user, silent=silent)
            except Exception as e:
                db.rollback()
                logger.error(f"Error checking achievements of {user.username}: {e}")
                failures.append(user.username)
        elapsed_time = time.time() - start_time
        if elapsed_time > 30:
            await utils.send_message_to_admins(
                db, "❗Ejecución lenta❗\nLa última comprobación ha durado más de 30 segundos"
            )
        logger.info("Elapsed time: " + str(elapsed_time))
        if failures:
            await utils.send_message_to_admins(
                db, "Error checking achievements of: " + ", ".join(failures)
            )
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
    stopped: tuple | None = None,
    recalculate: list[int] | None = None,
):
    """Background-task entrypoint for routers/timers.py and the admin panel.

    Deliberately a plain `def`: Starlette runs it in a worker thread. The checks are a
    long chain of blocking DB/OpenAI calls wrapped in async functions, so running them
    on the event loop would freeze every other request until they finished. It gets its
    own DB session (the request-scoped one is already closed by the time a
    BackgroundTask runs) and its own event loop.

    `ranking_before` is the snapshot taken before the change (see ranking_snapshot); when
    given and not silent, the ranking changes it caused are announced. `stopped` is (game_id, start,
    duration in seconds) of the timer that has just been stopped: what only a real timer can earn
    ("Lo he abierto sin querer") is judged from it, never from the sessions in the database.

    `recalculate` is the seasons of a session that was added, edited or deleted: instead of only adding what
    the user has earned, their achievements of those seasons are worked out again, so what the session
    earned and no longer holds is revoked (see crud/achievements_recalc.py). What it adds is announced unless
    `silent` (an admin's changes are silent); a revocation never is.
    """
    from ..database.database import SessionLocal

    async def _run():
        db = SessionLocal()
        try:
            if recalculate:
                from ..crud import achievements_recalc  # imports this module too

                await achievements_recalc.recalculate_user(db, user_id, recalculate, notify=not silent)
            else:
                await check_users(db, silent=silent, user_ids=None if user_id is None else [user_id])
            if stopped is not None:
                user = users.get_user_by_id(db, user_id)
                if user is not None:
                    await achievements.opened_by_mistake(db, user, *stopped, silent=silent)
            if ranking_before is not None:
                await announce_ranking_changes(db, ranking_before, silent)
            if not silent:
                await announce_challenge_totals(db)
        finally:
            db.close()

    with _check_lock:
        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error("Error checking after a session change: " + str(e))


def after_timer_start(user_id: int, start_time: datetime.datetime, new_game_id: str | None = None):
    """Background-task entrypoint for a timer that has just started.

    Only what a running timer can unlock is checked here (the rest needs a finished
    session and is checked when it stops): the time of day and the date it started at
    (early riser, nocturnal, new year, the game's release day, and the achievements about the world outside the app) and teamwork and "all together", which count the
    timers running right now. `new_game_id` is set when it is the
    first time the user plays that game this season: the group hears about it here, so the
    request that started the timer does not wait for the notification.
    """
    from ..database.database import SessionLocal

    async def _run():
        db = SessionLocal()
        try:
            user = users.get_user_by_id(db, user_id)
            if user is not None:
                timer = time_entries.get_active_game_timer_by_user(db, user_id)
                game_id = timer.game_id if timer is not None else None
                await send_timer_notice(db, timer)
                if new_game_id is not None:
                    game = games.get_game_by_id(db, new_game_id)
                    if game is not None:
                        await users.announce_new_game(db, user, game, start_time.date(), silent=False)
                await achievements.timer_started(db, user, start_time, game_id)
                await achievements.user_played_total_games(db, user)
                started = [Played(game_id, start_time)] if game_id is not None else []
                for view in achievements.lifetime_views(db):
                    await view.user_played_total_games(db, user)
                    # the world outside the app: the day, the sky, the weather and the age of the game at this very start
                    await view.external_days(db, user, played=started)
                    await view.weather(db, user, played=started)
                    await view.archaeologist(db, user, played=started)
                    await view.birth_year_game(db, user, played=started)
                if game_id is not None:
                    await achievements.all_together(db, game_id, silent=False)
            await achievements.teamwork(db, silent=False)
        finally:
            db.close()

    with _check_lock:
        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error("Error checking after a timer start: " + str(e))


def after_timer_stop(user_id: int, game_id: str, duration_seconds: int | None):
    """Background-task entrypoint for a timer that has just stopped: unpins its notification on the
    user's devices. Apart from after_session_change (which is slow and serialized) so it arrives at once."""
    from ..database.database import SessionLocal

    async def _run():
        with SessionLocal() as db:
            game = games.get_game_by_id(db, game_id)
            await push.notify_timer_stopped(user_id, game.name if game else "", duration_seconds)

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("Error unpinning the timer notification: " + str(e))


def after_completion(entry_id: int, silent: bool = False):
    """Background-task entrypoint for a completed library entry: average time, achievements and the
    group announcement. Best effort: the completion itself is already saved."""
    from ..database.database import SessionLocal

    async def _run():
        db = SessionLocal()
        try:
            entry = db.get(models.UserGame, entry_id)
            if entry is not None:
                await users.after_completion(db, entry, silent)
        finally:
            db.close()

    with _check_lock:
        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error("Error in post-completion tasks: " + str(e))


async def announce_lost_streaks(db: Session, today: datetime.date | None = None, silent: bool = False):
    """Daily: announce the streaks of more than 10 days that were lost. It is the one thing nothing
    else can trigger: a streak is lost on a day nobody plays."""
    today = today or datetime.date.today()
    for user in users.get_users(db):
        lost = streaks.lost_streak(time_entries.get_played_days(db, user.id), today)
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
        "players": [row["user_id"] for row in rankings.user_hours_players(db, is_active=True)],
        "games": [row["game_id"] for row in time_entries.games_played_time(db, is_active=True)],
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
        hours = utils.format_duration(player["played_time"] or 0)
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
        msg += f"{position}. {name}: {utils.format_duration(game['played_time'])} ({arrow})\n"
    # a game that was in the top 10 and is now 11th has fallen out of it
    if len(games_now) > 10 and previous.get(games_now[10]["game_id"], 11) < 11:
        dropped = games_now[10]
        msg += "----------\n"
        msg += f"11. {dropped['name']}: {utils.format_duration(dropped['played_time'])} (💀)\n"
    return msg


async def announce_ranking_changes(db: Session, before: dict, silent: bool):
    """Announce how the players and games rankings moved since `before` (a ranking_snapshot)."""
    if silent:
        return
    try:
        message = games_ranking_message(before["games"], time_entries.games_played_time(db, is_active=True))
        if message:
            logger.info(message)
            await utils.send_message(message, silent, ai_use="ranking_games")
        message = players_ranking_message(before["players"], rankings.user_hours_players(db, is_active=True))
        if message:
            logger.info(message)
            await utils.send_message(message, silent, ai_use="ranking_players")
    except Exception as e:
        logger.error("Error announcing ranking changes: " + str(e))


##################
##### OTHERS #####
##################


async def check_forgotten_timer(db: Session, user: models.User):
    """Remind a user about a timer running for too long (the scheduler calls this hourly, and each
    timer is reminded about once: in the run that follows it crossing the line).

    "Too long" is the user's own setting, or the default when they never set it. The notice goes
    only through the channels they left on (both off: no notice).
    """
    telegram_on, push_on = user_settings.forgotten_timer_channels(db, user.id)
    if not ((telegram_on and user.telegram_id is not None) or (push_on and push_has_devices(user.id))):
        return
    hours = user_settings.forgotten_timer_hours(db, user.id)
    forgotten_timer = time_entries.get_forgotten_game_timers(
        db, user_id=user.id, hours=hours, newly_forgotten=True
    )
    if forgotten_timer:
        logger.info(f"{user.name} has an active timer for more than {hours} hours")
        msg = (
            "Hola, "
            + user.name
            + f". Tienes un timer activo desde hace más de {hours} {'hora' if hours == 1 else 'horas'}."
            + " Si es correcto, sigue disfrutando. Si te has olvidado de pararlo,"
            + " párala y edita la sesión con el tiempo correcto."
        )
        await utils.send_message_to_user(user.telegram_id, msg, user_id=user.id, telegram_on=telegram_on, push_on=push_on)


def join_names(names: list[str]) -> str:
    """"A", "A y B", "A, B y C"."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def wishlist_release_message(releases: list[tuple[str, list[str]]]) -> str:
    """The notice for a player whose wished games come out today: (game, other players who want it) for each.
    One block per game; the first line of the first one is what a push shows as its title."""
    blocks = []
    for game_name, others in releases:
        block = f"¡Hoy sale *{utils.escape_markdown(game_name)}*! Estaba en tu lista de deseados."
        if others:
            verb = "lo espera" if len(others) == 1 else "lo esperan"
            block += f"\nTambién {verb} {utils.escape_markdown(join_names(others))}."
        blocks.append(block)
    return "\n\n".join(blocks)


async def check_wishlist(db: Session, today: datetime.date) -> str:
    """Daily: refresh the release date of the games somebody is waiting for (they slip), then tell each player
    which of the games they wished come out today (while WISHLIST_PRIVATE_NOTICE is on). Nothing is remembered:
    a game comes out on one day only."""
    changed = await asyncio.to_thread(rawg_sync.refresh_release_dates, db, wishlist.to_refresh(db, today))
    if not WISHLIST_PRIVATE_NOTICE:
        return f"{len(changed)} dates changed"
    per_user: dict[int, tuple[models.User, list]] = {}
    for user, game, others in wishlist.releases_on(db, today):
        per_user.setdefault(user.id, (user, []))[1].append((game.name, [w["name"] for w in others]))
    for user, releases in per_user.values():
        if user.telegram_id is None and not push_has_devices(user.id):
            continue
        await utils.send_message_to_user(user.telegram_id, wishlist_release_message(releases), user_id=user.id)
    return f"{len(changed)} dates changed, {len(per_user)} users told"


def wishlist_eve_message(releases: list[tuple[str, list[str]]]) -> str:
    """The notice for the group the day before: (game, players who wait for it) for each game coming out tomorrow."""
    blocks = []
    for game_name, waiting in releases:
        blocks.append(
            f"Mañana sale *{utils.escape_markdown(game_name)}*. "
            f"Está en la lista de deseados de {utils.escape_markdown(join_names(waiting))}."
        )
    return "\n\n".join(blocks)


async def announce_wishlist_eve(db: Session, tomorrow: datetime.date) -> str:
    """The day before a game comes out, tell the group which wished games do (one message for all of them).
    The AI may rewrite it (`wishlist_release`). Nothing is remembered: a game comes out on one day only."""
    releases = [(game.name, waiting) for game, waiting in wishlist.wished_releases_on(db, tomorrow)]
    if releases:
        await utils.send_message(wishlist_eve_message(releases), False, ai_use="wishlist_release")
    return f"{len(releases)} games"


async def announce_challenge_launch(db: Session, challenge_id: int) -> str:
    """Tell the group a challenge has been launched (the admin chose to)."""
    challenge = db.get(models.Challenge, challenge_id)
    if challenge is None:
        return "gone"
    template = challenges.TEMPLATES[challenge.kind]
    title = utils.escape_markdown(challenge.title)
    await utils.send_message(f"🎯 *Nuevo reto del grupo*\n*{title}*\n{template.summary(challenge)}", False)
    return "sent"


async def announce_challenge_totals(db: Session, today: datetime.date | None = None) -> int:
    """Tell the group which running challenges have just reached their total. Said once per challenge: the moment is
    recorded (`total_notified_at`) before the next check can say it again."""
    sent = 0
    for challenge, progress in challenges_crud.reached_totals(db, today or datetime.date.today()):
        challenge.total_notified_at = datetime.datetime.now()
        db.commit()
        template = challenges.TEMPLATES[challenge.kind]
        title = utils.escape_markdown(challenge.title)
        await utils.send_message(f"🏆 *¡Reto cumplido!*\n*{title}*\n{template.reached(challenge, progress)}", False)
        sent += 1
    return sent


def after_challenge_launch(challenge_id: int):
    """Background-task entrypoint for a challenge that has just been launched."""
    from ..database.database import SessionLocal

    async def _run():
        with SessionLocal() as db:
            await announce_challenge_launch(db, challenge_id)

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("Error announcing a challenge: " + str(e))


async def send_timer_notice(db: Session, timer: models.GameTimer | None):
    """Show or refresh the pinned push notification of one running timer."""
    if timer is None:
        return
    game = games.get_game_by_id(db, timer.game_id)
    await push.notify_timer(timer.user_id, game.name if game else "", timer.start_time)


def timer_notice_due(slot: datetime.datetime, start_time: datetime.datetime, every_minutes: int) -> bool:
    """Is the notification of a timer started at `start_time` due for the minute `slot`?

    It is, once per `every_minutes` of play (never at minute 0: it was shown when the timer started).
    Whole minutes between the minute of the start and the minute of the slot, so it does not depend
    on the second the scheduler happens to run at and nothing has to be remembered between runs.
    """
    played = int((slot - start_time.replace(second=0, microsecond=0)).total_seconds() // 60)
    return played >= every_minutes and played % every_minutes == 0


async def refresh_timer_notices(db: Session, slot: datetime.datetime) -> str:
    """Refresh the pinned notification of the running timers that are due at `slot`, each one
    at its user's own interval (user_settings.timer_notice_minutes). Called every minute by the scheduler."""
    if not push.is_ready():
        return ""
    due = [
        timer
        for timer in time_entries.get_running_game_timers(db)
        if timer_notice_due(slot, timer.start_time, user_settings.timer_notice_minutes(db, timer.user_id))
    ]
    for timer in due:
        await send_timer_notice(db, timer)
    return f"{len(due)} timers"


def signed_difference(difference: int, render=str) -> str:
    """"+3", "-2" or "=" for the change of a figure since the week before."""
    if difference == 0:
        return "="
    return ("+" if difference > 0 else "-") + render(abs(difference))


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
        logger.info("Weekly resume sessions:")
        logger.info("This week: " + str(weekly_sessions))
        logger.info("Last week: " + str(last_weekly_sessions))
        sessions_diff = int(weekly_sessions) - int(last_weekly_sessions)
        sessions_diff = signed_difference(sessions_diff)
        logger.info("Weekly resume games:")
        logger.info("This week: " + str(weekly_games))
        logger.info("Last week: " + str(last_weekly_games))
        games_diff = int(weekly_games) - int(last_weekly_games)
        games_diff = signed_difference(games_diff)
        logger.info("Weekly resume achievements:")
        logger.info("This week: " + str(weekly_achievements))
        logger.info("Last week: " + str(last_weekly_achievements))
        achievements_diff = int(weekly_achievements) - int(last_weekly_achievements)
        achievements_diff = signed_difference(achievements_diff)
        msg = (
            "🤖 *Aquí está tu resumen semanal* 🤖\n"
            + "Horas: "
            + utils.format_duration(weekly_hours)
            + " ("
            + signed_difference(hours_diff, utils.format_duration)
            + ")\n"
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

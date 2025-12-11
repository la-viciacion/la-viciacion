import datetime
import json
import re
import time
from typing import Union

import requests
from sqlalchemy import asc, create_engine, desc, func, select, text, update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import clockify, games, rankings, time_entries, users
from ..crud.achievements import Achievements
from ..database import models, schemas
from . import my_utils as utils
from .clockify_api import ClockifyApi
from ..utils import ai_prompts as prompts
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

clockify_api = ClockifyApi()
config = Config()
achievements = Achievements()


########################
##### BASIC ROUTES #####
########################


async def sync_data(
    db: Session,
    user_clfy_id: str = None,
    sync_season: bool = False,
    silent: bool = False,
    sync_all: bool = False,
    only_acive_users: bool = True,
    only_time_entries: bool = False,
):
    # logger.info("Sync data...")
    logger.info(only_acive_users)
    logger.info(only_time_entries)
    logger.info(silent)
    current_season = datetime.datetime.now().year
    current_date = datetime.datetime.now()
    start_time = time.time()
    week_day = current_date.weekday()
    hour = current_date.hour
    minute = current_date.minute
    start_date = None
    if silent is True:
        silent = True
    else:
        silent = False
    if not only_time_entries:
        if sync_season:
            start_date = str(current_date.year) + "-01-01"
            silent = True
            logger.info("Sync data from " + str(start_date))
            logger.info("Cleaning season tables...")
            # db.query(models.TimeEntry).delete()
            db.query(models.UserGame).delete()
            # db.query(models.UserAchievement).delete()
            db.query(models.UserStatistics).delete()
            db.query(models.GameStatistics).delete()
            db.commit()
        if sync_all:
            start_date = config.INITIAL_DATE
            silent = True
            logger.info("Sync ALL data from " + str(start_date))
            # logger.info("Cleaning season and historical tables...")
            # db.query(models.TimeEntry).delete()
            # db.query(models.TimeEntryHistorical).delete()
            db.query(models.UserGame).delete()
            # db.query(models.UserGameHistorical).delete()
            # db.query(models.UserAchievement).delete()
            # db.query(models.UserAchievementHistorical).delete()
            db.query(models.UserStatistics).delete()
            # db.query(models.UserStatisticsHistorical).delete()
            db.query(models.GameStatistics).delete()
            # db.query(models.GameStatisticsHistorical).delete()
            db.commit()
            # logger.info("Sync ALL data from " + start_date + "...")
    else:
        start_date = config.INITIAL_DATE
        only_acive_users = False
        silent = True
        logger.info("Sync ONLY time entries from " + str(start_date))

    achievements = Achievements(silent)
    clockify.sync_clockify_tags(db)
    achievements.populate_achievements(db)
    users_db = users.get_users(db, only_acive_users)
    # Clear tables on new year (season)
    if current_date.month == 1 and current_date.day == 1:
        start_date = str(current_date.year) + "-01-01"
        if current_date.hour == 0 and current_date.minute == 0:
            # logger.debug("Clear current season tables...")
            silent = True
            # db.query(models.TimeEntry).delete()
            # db.query(models.UserGame).delete()
            # db.query(models.UserAchievement).delete()
            db.query(models.UserStatistics).delete()
            db.query(models.GameStatistics).delete()
            db.commit()
    logger.info("Current season: " + str(current_season))
    logger.info("Silent mode: " + str(silent))
    # logger.info("Sync clockify entries...")
    # delete_older_timers(db)
    try:
        if user_clfy_id is not None:
            try:
                user_db = users.get_user_by_clockify_id(db, user_clfy_id)
                if user_db:
                    users_db = [user_db]
                    # logger.debug("Delete older timers for " + str(user_db.name) + "...")
                    # delete_older_active_timers(db, user_db)
                    delete_older_timers(db, user_db)
                else:
                    logger.warning("User not found")
                    return
            except Exception as e:
                logger.error(e)
                logger.error("Error deleting timers for user " + str(user_clfy_id))
        else:
            # logger.debug("Delete older timers for all users...")
            # delete_older_active_timers(db)
            delete_older_timers(db)
        logger.info("########################")
        logger.info("##### USER CHECKS ######")
        logger.info("########################")
        for user in users_db:
            if user.name is not None and user.name != "":
                user_name = str(user.name)
            else:
                user_name = str(user.username)
            # logger.info("#### " + str(user_name) + " ####")

            # Create user statistics entry (if needed)
            users.create_user_statistics(db, user.id)
            users.create_user_statistics_historical(db, user.id)

            # Update clockify_id for user if has not been set and email matches with a valid user on Clockify
            if user.clockify_id is None or not utils.check_hex(user.clockify_id):
                users.update_clockify_id(
                    db, user.username, clockify_api.get_user_by_email(user.email)
                )

            # Sync time_entries from Clockify with local DB
            # logger.debug("Sync clockify entries for " + str(user_name) + "...")
            total_entries = await utils.sync_clockify_entries(
                db, user, start_date, only_time_entries, silent
            )

            # If only_time_entries is True, skip the rest of the checks and calculations
            if only_time_entries:
                # logger.info("Only time entries sync")
                continue
            # logger.info("THIS NOT SHOULD BE PRINTED")

            # if total_entries < 1:
            #     # logger.debug("No time entries for " + str(user_name))
            #     continue

            calculation_start_time = time.time()

            # Update some user statistics
            # logger.debug("Updating played days...")
            played_days_season, real_played_days_season = time_entries.get_played_days(
                db, user.id
            )
            # logger.info("Played days: " + str(len(played_days_season)))
            # logger.info("Real played days: " + str(len(real_played_days_season)))
            users.update_played_days(db, user.id, len(real_played_days_season))
            # Check played days achievement
            await achievements.user_played_total_days(
                db, user, real_played_days_season, silent=silent
            )
            # logger.debug("Checking streaks for " + user.name)
            (
                best_streak_date,
                best_streak,
                current_streak,
                best_unplayed_streak_date,
                best_unplayed_streak,
                current_unplayed_streak,
            ) = streak_days(db, user, real_played_days_season, current_season)
            # logger.info("Max gap: " + str(best_unplayed_streak))
            # logger.info("Max gap date: " + str(best_unplayed_streak_date))
            # logger.info("Current gap: " + str(current_unplayed_streak))
            # return
            await check_streaks(db, user, current_streak, best_streak, silent=silent)
            # TODO: Check streaks achievement
            users.update_streaks(
                db,
                user.id,
                current_streak,
                best_streak,
                best_streak_date,
                best_unplayed_streak,
                best_unplayed_streak_date,
                current_unplayed_streak,
            )
            # logger.debug("Updating played time games and check achievements...")
            played_time_games = time_entries.get_user_games_played_time(db, user.id)
            for game in played_time_games:
                if game[1] is not None:
                    users.update_played_time_game(db, user.id, game[0], game[1])
                    await achievements.user_played_hours_game(
                        db=db,
                        user=user,
                        game_id=game[0],
                        played_time=game[1],
                        silent=silent,
                    )
            # logger.debug("Updating played time...")
            played_time = time_entries.get_user_played_time(db, user.id)
            if played_time is not None:
                played_time = played_time[1]
            else:
                played_time = 0
            users.update_played_time(db, user.id, played_time)
            # Other achievements
            await achievements.user_played_total_time(
                db, user, played_time, silent=silent
            )
            await achievements.user_session_time(db, user, silent=silent)
            await achievements.user_played_total_games(db, user, silent=silent)
            await achievements.user_streak(
                db, user, best_streak, best_streak_date, silent=silent
            )
            await achievements.user_played_day_time(db, user, silent)
            await achievements.happy_new_year(db, user, silent)
            await achievements.early_riser(db, user, silent)
            await achievements.nocturnal(db, user, silent)
            await check_forgotten_timer(db, user)
            calculation_end_time = time.time()
            calculation_elapsed_time = calculation_end_time - calculation_start_time
            logger.debug("Time spent on calculations: " + str(calculation_elapsed_time))

        # If only_time_entries is True, skip the rest of the checks and calculations
        if not only_time_entries:
            # logger.info("Only time entries sync")

            logger.info("#########################")
            logger.info("#### GENERAL CHECKS #####")
            logger.info("#########################")

            # Update some game statistics
            # logger.debug("Updating played time for games...")
            played_time_games = time_entries.get_games_played_time(db)
            for game in played_time_games:
                games.update_total_played_time(db, game[0], game[1])

            # Check rankings
            # Notifications enabled
            await ranking_games_hours(db, silent=silent)
            await ranking_players_hours(db, silent=silent)

            # Notifications disabled
            # await ranking_games_hours(db, silent=True)
            # await ranking_players_hours(db, silent=True)

            # Others
            await achievements.teamwork(db, silent)
            users_db = users.get_users(db)
            # Check weekly resume only on monday at 9:00
            if week_day == 0 and hour == 9 and minute == 0:
                for user in users_db:
                    await weekly_resume(db, user, weeks_ago=1, silent=silent)

        end_time = time.time()
        elapsed_time = end_time - start_time

        if elapsed_time > 30 and (not sync_all and not sync_season):
            msg = (
                "❗Ejecución lenta❗\n"
                + "La última ejecución ha durado más de 30 segundos"
            )
            await utils.send_message_to_admins(db, msg)
        logger.info("Elapsed time: " + str(elapsed_time))
    except Exception as e:
        logger.error("Error on sync: " + str(e))
        await utils.send_message_to_admins(db, "Error on sync: " + str(e))


def streak_days(
    db: Session,
    user: models.User,
    played_dates: list[models.TimeEntry],
    current_season: int,
):
    """
    TODO:
    """
    max_streak = 0
    start_streak_date = None
    end_max_streak_date = None
    current_streak = 0
    try:
        if len(played_dates) == 0:
            end_max_streak_date = datetime.datetime.strptime(
                str(current_season) + "-01-01", "%Y-%m-%d"
            )
            return end_max_streak_date, 0, 0, end_max_streak_date, 0, 0
        elif len(played_dates) == 1:
            end_max_streak_date = played_dates[0]
            max_streak = 1
            current_streak = 1
        for i in range(1, len(played_dates)):
            # Check diff between current and last date
            diff = (played_dates[i] - played_dates[i - 1]).days
            if diff == 1:
                if current_streak == 0:
                    start_streak_date = played_dates[i - 1]
                current_streak += 1
            else:
                if current_streak >= max_streak:
                    max_streak = current_streak
                    end_max_streak_date = played_dates[i - 1]
                current_streak = 0
        # Check last date to add this day to the streak. If last d
        today = datetime.date.today()
        # Add last elem to streak if its yesterday
        if (today - played_dates[-1]).days == 1:
            current_streak += 1
        # Add today to streak if the last elem is today
        if (today - played_dates[-1]).days == 0:
            current_streak += 1

        # Check if current streak (with today) is longer than best (without today)
        if current_streak > max_streak:
            max_streak = current_streak
            end_max_streak_date = played_dates[-1]

        # Check is there is more than 1 day without play
        if (today - played_dates[-1]).days > 1:
            current_streak = 0
    except Exception as e:
        logger.error("Error calculating streak days: " + str(e))

    # Unplayed days
    max_gap = 0
    end_max_gap_date = None
    current_gap = 0

    try:
        for i in range(1, len(played_dates)):
            gap = (played_dates[i] - played_dates[i - 1]).days - 1
            if gap > 0:
                # Update current gap
                current_gap = gap
                # Update max gap
                if gap >= max_gap:
                    max_gap = gap
                    end_max_gap_date = played_dates[i]

        # Check unplayed days for today
        last_gap = (today - played_dates[-1]).days - 1
        if last_gap > 0:
            current_gap = last_gap
            # If last gap is longer than max gap, update max gap
            if last_gap > max_gap:
                max_gap = last_gap
                end_max_gap_date = today
    except Exception as e:
        logger.error("Error calculating unplayed days: " + str(e))

    return (
        end_max_streak_date,
        max_streak,
        current_streak,
        end_max_gap_date,
        max_gap,
        current_gap,
    )


async def check_streaks(
    db: Session,
    user: models.User,
    current_streak: int,
    best_streak: int,
    silent: bool = False,
):
    hour = datetime.datetime.now().hour
    minutes = datetime.datetime.now().minute
    # Check if user lose streak
    current_db_streaks_data = users.get_streaks(db, user.username)[0]
    # logger.info(current_streaks_data[0])
    current_db_streak = current_db_streaks_data[0]
    best_db_streak = current_db_streaks_data[1]
    best_db_streak_date = current_db_streaks_data[2]
    if (
        current_db_streak is not None
        and current_streak == 0
        and current_db_streak > 10
        and hour == 5
        and minutes == 0
    ):
        msg = (
            user.name
            + " acaba de perder la racha de "
            + str(current_db_streak)
            + " días."
        )
        logger.info(msg)
        await utils.send_message(msg, silent)
    # TODO: Check this to avoid daily notifications when the streak is not lost
    # if best_db_streak is not None and best_streak > best_db_streak:
    #     msg = (
    #         user.name
    #         + " acaba de superar su mejor racha de "
    #         + str(best_db_streak)
    #         + " días."
    #     )
    #     logger.info(msg)
    #     await utils.send_message(msg, silent)


####################
##### RANKINGS #####
####################


async def ranking_games_hours(db: Session, silent: bool):
    # logger.debug("Checking games ranking hours...")
    try:
        msg = ""
        most_played_games = games.get_most_played_time(db, 11)
        most_played: list[models.GameStatistics] = []
        most_played_to_check = []  # Only for easy check with current ranking
        for game in most_played_games:
            most_played.append(game)
            most_played_to_check.append(game.game_id)
        result = games.current_ranking_hours(db)
        current: list[models.Game] = []
        current_to_check = []  # Only for easy check with most played
        for game in result:
            current.append(game)
            current_to_check.append(game.game_id)
        if current_to_check[:10] == most_played_to_check[:10]:
            msg = "No changes in TOP 10 games ranking"
            logger.info("No changes in TOP 10 games ranking")
        else:
            logger.info("Changes in TOP 10 games ranking")
            msg = "📣 Actualización del ránking de juegos 📣\n"
            i = 0
            for game in most_played:
                if i <= 10:
                    game_name = games.get_game_by_id(db, game.game_id).name
                    time = game.played_time
                    current = game.current_ranking
                    diff_raw = current - (i + 1)
                    diff = str(diff_raw)
                    # This adds '+' sign to games that up position (positive diff has not '+' sign)
                    if diff_raw > 0:
                        diff = "+" + diff
                    diff = diff.replace("+", "↑")
                    diff = diff.replace("-", "↓")
                    if diff != "0":
                        game_name = "*" + game_name + "*"
                    else:
                        diff = diff.replace("0", "=")
                    if diff_raw > 1:
                        game_name = "🔥 " + game_name
                    if diff_raw == 1:
                        game_name = "⬆️ " + game_name
                    if diff_raw < 0:
                        if diff_raw < -1:
                            game_name = "🔻 " + game_name
                        else:
                            game_name = "⬇️ " + game_name
                    # Only to check if game has fall of the top10
                    # Then, always break
                    if i == 10 and "↓" in diff:
                        msg = msg + "----------\n"
                        msg = (
                            msg
                            + str(i + 1)
                            + ". "
                            + game_name
                            + ": "
                            + str(utils.convert_time_to_hours(time))
                            + " ("
                            + "💀"
                            + ")"
                            + "\n"
                        )
                        break
                    elif i < 10:
                        msg = (
                            msg
                            + str(i + 1)
                            + ". "
                            + game_name
                            + ": "
                            + str(utils.convert_time_to_hours(time))
                            + " ("
                            + diff
                            + ")"
                            + "\n"
                        )
                    if i == 10:
                        break
                i += 1
            await utils.send_message(
                msg, silent, openai=True, system_prompt=prompts.RANKING_GAMES_PROMPT
            )
            logger.info(msg)
    except Exception as e:
        logger.error("Error in check ranking games: " + str(e))
    # logger.debug("Updating games ranking...")
    most_played = games.get_most_played_time(db)
    i = 1
    for game in most_played:
        games.update_current_ranking_hours(db, i, game.game_id)
        i += 1


async def ranking_players_hours(db: Session, silent: bool):
    # logger.debug("Ranking player hours...")
    played_time_db = users.played_time(db)
    most_played: list[models.User] = []
    most_played_to_check = []  # Only for easy check with current ranking
    for player in played_time_db:
        most_played.append(player)
        most_played_to_check.append(player.user_id)
    current_ranking_db = users.current_ranking_hours(db)
    current: list[models.User] = []
    current_to_check = []  # Only for easy check with most played
    for player in current_ranking_db:
        current.append(player)
        current_to_check.append(player.user_id)
    if current_to_check == most_played_to_check:
        logger.info("No changes in player ranking")
    else:
        logger.info("Changes in player ranking")
        msg = "📣 Actualización del ránking de horas 📣\n"
        for i, player in enumerate(played_time_db):
            name = str(users.get_user_by_id(db, player.user_id).name)
            hours = player.played_time
            if hours is None:
                hours = 0
            current = player.current_ranking_hours
            diff_raw = current - (i + 1)
            diff = str(diff_raw)
            # This adds '+' sign to games that up position (positive diff has not '+' sign)
            if diff_raw > 0:
                diff = "+" + diff
            diff = diff.replace("+", "↑")
            diff = diff.replace("-", "↓")
            if diff != "0":
                name = "*" + str(name) + "*"
            else:
                diff = diff.replace("0", "=")
            if diff_raw > 1:
                name = "🔥 " + name
            if diff_raw == 1:
                name = "⬆️ " + name
            if diff_raw < 0:
                if diff_raw < -1:
                    name = "🔻 " + name
                else:
                    name = "⬇️ " + name
            msg = (
                msg
                + str(i + 1)
                + ". "
                + name
                + ": "
                + str(utils.convert_time_to_hours(hours))
                + " ("
                + diff
                + ")"
                + "\n"
            )
            users.update_current_ranking_hours(db, i + 1, player.user_id)
        await utils.send_message(
            msg, silent, openai=True, system_prompt=prompts.RANKING_USER_PROMPT
        )
        logger.info(msg)
    # logger.debug("Updating players ranking...")
    current_ranking = users.current_ranking_hours(db)
    i = 1
    for user in current_ranking:
        users.update_current_ranking_hours(db, i, user.user_id)
        i += 1


##################
##### OTHERS #####
##################


async def check_forgotten_timer(db: Session, user: models.User):
    # logger.debug("Check forgotten timers...")
    current_time = datetime.datetime.now().time()
    minutes = current_time.minute
    active_timer = time_entries.get_forgotten_timer_by_user(db, user)
    if active_timer is not None and (minutes == 0):
        logger.info(user.name + " has an active timer for more than 4 hours")
        msg = (
            "Hola, "
            + user.name
            + ". Tienes un timer activo desde hace más de 4 horas."
            + " Si es correcto, sigue disfrutando. Si te has olvidado de pararlo,"
            + " por favor, descartalo (no lo pares, tienes una"
            + " opción para descartar sin guardar) y añade una entrada a mano con el tiempo correcto."
        )
        await utils.send_message_to_user(user.telegram_id, msg)


def delete_older_active_timers(db: Session, user: models.User = None):
    current_time = datetime.datetime.now().time()
    minutes = current_time.minute
    active_timers = time_entries.get_older_active_timers(db, user)
    for timer in active_timers:
        # logger.info("Deleting timer " + str(timer.id))
        db.delete(timer)
        db.commit()


def delete_older_timers(db: Session, user: models.User = None):
    current_time = datetime.datetime.now().time()
    minutes = current_time.minute
    active_timers = time_entries.get_older_active_timers(db, user)
    for timer in active_timers:
        # logger.info("Deleting timer " + str(timer.id))
        db.delete(timer)
        db.commit()


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
        # current_ranking = rankings.user_current_ranking(db, user)
        # current_ranking = str(current_ranking[0][0])
        msg = (
            "🤖*Aquí está tu resumen semanal*********🤖\n"
            # + "Ranking actual: "
            # + current_ranking
            # + "\n"
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
            await utils.send_message_to_user(user.telegram_id, msg)
        resume["ranking"] = current_ranking
        resume["hours"] = weekly_hours
        resume["sessions"] = weekly_sessions
        resume["games"] = weekly_games
        resume["achievements"] = weekly_achievements
        return resume
    except Exception as e:
        logger.error("Error sending weekly resume to user " + user.name + ": " + str(e))

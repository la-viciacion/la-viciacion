import json

import requests
import utils.keyboard as kb
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import ContextTypes, ConversationHandler
from utils.config import Config
from utils.duration import format_duration
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


class RankingRoutes:
    async def rankings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Ranking")
        query = update.callback_query
        await query.answer()
        keyboard = kb.RANKING_MENU
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Elije un ranking:", reply_markup=reply_markup
        )
        return utils.RANKING_ROUTES

    async def user_hours(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking hours")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_hours"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Así está el ranking de horas de vicio:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(format_duration(elem["played_time"]))
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_days(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking days")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_days"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Así está el ranking de días de vicio:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["played_days"])
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_played_games(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking played")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_played_games"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking de juegos jugados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["played_games"])
                + "\n"
            )

        await utils.response_conversation(update, context, msg)

    async def user_achievements(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking achievements")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=achievements"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking de logros:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["achievements"])
                + "\n"
            )

        await utils.response_conversation(update, context, msg)

    async def user_best_streak(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking streak")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_best_streak"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Así va el ranking de racha de días:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["best_streak"])
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_current_streak(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking current streak")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_current_streak"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Estas son las rachas de días actuales:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["current_streak"])
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_ratio(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking ratio")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_ratio"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Así está el ranking de ratio (completados / jugados):\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["ratio"])
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_completed_games(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking completed games")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_completed_games"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking de juegos completados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(elem["completed_games"])
                + "\n"
            )

        await utils.response_conversation(update, context, msg)

    async def games_most_played(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking most played")
        ranking = utils.fetch_json(
            "GET", config.API_URL + "/statistics/rankings?ranking=games_most_played"
        )
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking de juegos más jugados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(format_duration(elem["played_time"]))
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

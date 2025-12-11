import datetime

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
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


class MyRoutes:
    async def my_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        logger.info("My data")
        # db.log(context.user_data["user"], ActionLogs.MY_DATA)
        await query.answer()
        keyboard = kb.MY_DATA
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="¿Qué quieres consultar?", reply_markup=reply_markup
        )
        return utils.MY_ROUTES

    async def my_games(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("My games")
        query = update.callback_query
        username = query.from_user.username
        ranking = utils.make_request(
            "GET",
            config.API_URL + "/statistics/users/" + username + "?ranking=played_games",
        ).json()
        ranking = utils.load_json_response(ranking[0])
        num_games = len(ranking["data"])
        msg = f"Has jugado a {num_games} juegos. Estos son los 10 últimos:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["game_name"])
                + " ("
                + str(utils.convert_time_to_hours(elem["played_time"]))
                + ")"
                + "\n"
            )
            if i == 9:
                break
        await utils.response_conversation(update, context, msg)

    async def my_top_games(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("My top games")
        query = update.callback_query
        username = query.from_user.username
        ranking = utils.make_request(
            "GET",
            config.API_URL + "/statistics/users/" + username + "?ranking=top_games",
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Este es tu top de juegos:\n"
        for i, elem in enumerate(ranking["data"]):
            played_time = utils.convert_time_to_hours(elem["played_time"])
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["game_name"])
                + " - "
                + str(played_time)
                + "\n"
            )
            if i == 9:
                break
        await utils.response_conversation(update, context, msg)

    async def my_completed_games(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("My completed games")
        query = update.callback_query
        username = query.from_user.username
        ranking = utils.make_request(
            "GET",
            config.API_URL
            + "/statistics/users/"
            + username
            + "?ranking=completed_games",
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Estos son tus últimos juegos completados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = msg + str(i + 1) + ". " + str(elem["game_name"]) + "\n"

        await utils.response_conversation(update, context, msg)

    async def my_achievements(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("My achievements")
        query = update.callback_query
        username = query.from_user.username
        ranking = utils.make_request(
            "GET",
            config.API_URL + "/statistics/users/" + username + "?ranking=achievements",
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Estos son tus logros:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = msg + str(i + 1) + ". " + str(elem["title"]) + "\n"

        await utils.response_conversation(update, context, msg)

    async def my_streak(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("My streak")
        query = update.callback_query
        username = query.from_user.username
        ranking = utils.make_request(
            "GET",
            config.API_URL + "/statistics/users/" + username + "?ranking=streak",
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Estos son tus rachas:\n"
        data = ranking["data"]
        msg = msg + "Racha actual: " + str(data["current_streak"]) + "\n"
        msg = msg + "Mejor racha: " + str(data["best_streak"]) + "\n"
        msg = msg + "Fin mejor racha: " + str(data["best_streak_date"])

        await utils.response_conversation(update, context, msg)

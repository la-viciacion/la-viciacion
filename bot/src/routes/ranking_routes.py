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
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


class RankingRoutes:
    async def rankings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Ranking")
        # Uncomment the following code at the end of season
        # Remove 'if' if want to disable for everyone
        # if not context.user_data["is_admin"]:
        #     await utils.response_conversation(
        #         update,
        #         context,
        #         "Esta opción está desactivada hasta final de temporada.",
        #     )
        #     logger.info("Option deactivated")
        #     return
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_hours"
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Así está el ranking de horas de vicio:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(utils.convert_time_to_hours(elem["played_time"]))
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

    async def user_days(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking days")
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_days"
        ).json()
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_played_games"
        ).json()
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

    # async def ranking_platform(
    #     self, update: Update, context: ContextTypes.DEFAULT_TYPE
    # ) -> None:
    #     logger.info("Ranking platform")
    #     # db.log(context.user_data["user"], ActionLogs.RANKING_PLATFORM)
    #     db.cursor.execute(dbq.ranking_platform)
    #     result = db.cursor.fetchall()
    #     result = dict(sorted(result, key=lambda x: x[1], reverse=True))
    #     # logger.info(type(result))
    #     msg = "Así está el ranking por plataforma:\n"
    #     i = 0
    #     for elem in result:
    #         if i >= 5:
    #             break
    #         msg = msg + elem + ": " + str(result[elem]) + " juegos\n"
    #         i += 1
    #     await utils.response_conversation(update, context, msg)

    async def user_achievements(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking achievements")
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=achievements"
        ).json()
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_best_streak"
        ).json()
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_current_streak"
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Estas són las rachas de días actuales:\n"
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_ratio"
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Estas són las rachas de días actuales:\n"
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
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=user_completed_games"
        ).json()
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

    async def debt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("Ranking debt")
        await utils.response_conversation(update, context, "Deuda técnica: TBI")
        return

    async def games_last_played(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking last played")
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=games_last_played"
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking últimos juegos jugados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = msg + str(i + 1) + ". " + str(elem["name"]) + "\n"
        await utils.response_conversation(update, context, msg)

    async def games_most_played(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.info("Ranking most played")
        ranking = utils.make_request(
            "GET", config.API_URL + "/statistics/rankings?ranking=games_most_played"
        ).json()
        ranking = utils.load_json_response(ranking[0])
        msg = "Ranking de juegos más jugados:\n"
        for i, elem in enumerate(ranking["data"]):
            msg = (
                msg
                + str(i + 1)
                + ". "
                + str(elem["name"])
                + ": "
                + str(utils.convert_time_to_hours(elem["played_time"]))
                + "\n"
            )
        await utils.response_conversation(update, context, msg)

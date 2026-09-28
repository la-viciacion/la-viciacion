import telegram
import utils.keyboard as kb
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.config import Config
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()

GAME, RATE = range(20, 22)


class DataRoutes:
    async def update_data(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        if update.callback_query.message.chat_id < 0:
            await utils.response_conversation(
                update,
                context,
                "Esta opción sólo puede usarse en un chat directo con el bot",
            )
        else:
            logger.info("Update data menu...")
            query = update.callback_query
            await query.answer()
            keyboard = kb.DATA_ACTIONS
            reply_markup = ReplyKeyboardMarkup(
                keyboard,
                one_time_keyboard=True,
                input_field_placeholder="¿Quieres confirmar los datos?",
                resize_keyboard=True,
                selective=True,
            )
            await query.edit_message_text("Accediendo al menú de actualizar datos...")
            await query.message.reply_text(
                "Elije una opción:", reply_markup=reply_markup
            )
            return utils.EXCEL_STUFF

    #############################
    ####### COMPLETE GAME #######
    #############################

    async def complete_game(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("Complete game...")
        username = update.message.from_user.username
        url = config.API_URL + "/users/" + username + "/games?completed=false"
        played_games = utils.make_request("GET", url).json()
        keyboard = []
        # logger.info(played_games)
        for played_game in played_games:
            url = config.API_URL + "/games/" + str(played_game["game_id"])
            game = utils.make_request("GET", url).json()
            # logger.info(game)
            keyboard.append([game["name"]])
        keyboard.append(kb.CANCEL)
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            input_field_placeholder="",
            resize_keyboard=True,
            selective=True,
        )
        await update.message.reply_text(
            "¿Qué juego acabas de completar?", reply_markup=reply_markup
        )
        return utils.EXCEL_COMPLETE_GAME

    async def complete_game_validation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("Received game")
        message = update.message.text
        context.user_data[GAME] = message
        keyboard = kb.YES_NO
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            input_field_placeholder="",
            resize_keyboard=True,
            selective=True,
        )
        await update.message.reply_text(
            "¿Seguro que quieres marcar el juego *" + message + "* como completado?",
            reply_markup=reply_markup,
            parse_mode=telegram.constants.ParseMode.MARKDOWN,
        )
        return utils.EXCEL_CONFIRM_COMPLETED

    async def complete_game_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        try:
            if "Sí" in str(update.message.text):
                logger.info("Complete game confirmed")
                username = context.user_data["username"]
                url = config.API_URL + "/games?name=" + context.user_data[GAME]
                game_data = utils.make_request("GET", url).json()[0]
                logger.info("GAME ID: " + str(game_data["id"]))
                url = (
                    config.API_URL
                    + "/users/"
                    + username
                    + "/complete-game?game_id="
                    + str(game_data["id"])
                )
                response = utils.make_request("PATCH", url)
                if response.status_code == 200:

                    await update.message.reply_text(
                        "Juego" + " marcado como completado",
                        reply_markup=ReplyKeyboardRemove(),
                    )
                else:
                    await update.message.reply_text(
                        "Algo ha salido mal completando el juego: " + response.text,
                        reply_markup=ReplyKeyboardRemove(),
                    )

            else:
                await update.message.reply_text(
                    "Cancelada acción de completar juego",
                    reply_markup=ReplyKeyboardRemove(),
                )
        except Exception as e:
            await update.message.reply_text("Algo ha salido mal: " + str(e))
        return ConversationHandler.END

    #############################
    ######### RATE GAME #########
    #############################

    async def rate_game(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("Rate game...")
        username = update.message.from_user.username
        url = config.API_URL + "/users/" + username + "/games"
        played_games = utils.make_request("GET", url).json()
        keyboard = []
        games_list = []
        # logger.info(played_games)
        for played_game in played_games:
            url = config.API_URL + "/games/" + str(played_game["game_id"])
            game = utils.make_request("GET", url).json()
            # logger.info(game)
            games_list.append([game["name"]])
        games_list = sorted(games_list)
        for game in games_list:
            keyboard.append(game)
        keyboard.append(kb.CANCEL)
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            input_field_placeholder="",
            resize_keyboard=True,
            selective=True,
        )
        await update.message.reply_text(
            "Escoge el juego que quieras puntuar:", reply_markup=reply_markup
        )
        return utils.EXCEL_RATE_GAME

    async def rate_game_get_name(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        if "cancel" in update.message.text.lower():
            await utils.reply_message(update, context, "Pos nah.")
            return ConversationHandler.END
        context.user_data[GAME] = update.message.text
        logger.info("Received game: " + context.user_data[GAME])
        await update.message.reply_text(
            "¿Qué nota quieres darle? ¡CUIDAO! Si vas "
            + "a poner decimales, hazlo como una persona normal y usa una coma.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return utils.EXCEL_RATE_GAME_RATING

    async def rate_game_get_rating(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("Received rating")
        if update.message.text == "/cancel" or update.message.text.lower() == "cancel":
            await utils.reply_message(update, context, "Pos nah. Taluego.")
            return ConversationHandler.END
        message = update.message.text
        context.user_data[RATE] = message
        msg = "Juego: *" + context.user_data[GAME] + "*\n"
        msg += "Puntuación: " + str(context.user_data[RATE])
        keyboard = kb.YES_NO
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            input_field_placeholder="",
            resize_keyboard=True,
            selective=True,
        )
        await update.message.reply_text(
            "¿Quieres confirmar la siguiente información?\n\n" + msg,
            reply_markup=reply_markup,
            parse_mode=telegram.constants.ParseMode.MARKDOWN,
        )
        return utils.EXCEL_CONFIRM_RATE

    async def add_rating_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        try:
            if "Sí" in str(update.message.text):
                logger.info("Rate game confirmed")
                username = context.user_data["username"]
                url = config.API_URL + "/games?name=" + context.user_data[GAME]
                game_data = utils.make_request("GET", url).json()[0]
                logger.info("GAME ID: " + str(game_data["id"]))
                url = (
                    config.API_URL
                    + "/users/"
                    + username
                    + "/rate-game?game_id="
                    + game_data["id"]
                    + "&score="
                    + context.user_data[RATE]
                )
                logger.info(url)
                response = utils.make_request("PATCH", url)
                if response.status_code == 200:

                    await update.message.reply_text(
                        "Juego" + " puntuado correctamente.",
                        reply_markup=ReplyKeyboardRemove(),
                    )
                else:
                    await update.message.reply_text(
                        "Algo ha salido mal completando el juego: " + response.text,
                        reply_markup=ReplyKeyboardRemove(),
                    )
            else:
                await update.message.reply_text(
                    "Cancelada acción de puntuar juego",
                    reply_markup=ReplyKeyboardRemove(),
                )
        except Exception as e:
            await update.message.reply_text("Algo ha salido mal")
        return ConversationHandler.END

    async def cancel_data(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        logger.info("Closing excel menu...")
        await update.message.reply_text("Taluego!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

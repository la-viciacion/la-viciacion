import json

import requests
import utils.keyboard as kb
import utils.messages as msgs
from telegram import InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.config import Config
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


class BasicRoutes:
    async def activate_account(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.chat_id < 0:
            await utils.response_conversation(
                update,
                context,
                "Esta opción sólo puede usarse en un chat directo con el bot",
            )
        valid, user = utils.check_valid_chat(update)
        if valid:
            if user["is_active"]:
                await utils.reply_message(
                    update, context, "Tu cuenta ya ha sido activada"
                )
                return ConversationHandler.END
            keyboard = kb.ACTIVATE_ACCOUNT
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Hola "
                + update.message.from_user.first_name
                + ". Por favor, activa tu cuenta antes de usar el bot.",
                reply_markup=reply_markup,
            )
            return utils.ACTIVATE_ACCOUNT

    async def activate_account_validation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        try:
            query = update.callback_query
            await query.answer()
            response = utils.make_request(
                "GET",
                config.API_URL
                + "/activate/"
                + update.callback_query.from_user.username,
            )
            if response.status_code == 200:
                logger.info("Account validated")
                await query.edit_message_text(
                    text="Tu cuenta ha sido activada. Ya puedes usar el bot"
                )
                return ConversationHandler.END
            elif response.status_code == 409:
                await query.edit_message_text(text="Tu cuenta ya ha sido activada.")
                return ConversationHandler.END
        except Exception as e:
            logger.info(e)
            await query.edit_message_text(
                text="Algo ha salido mal activando la cuenta:" + str(e)
            )
            return ConversationHandler.END

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info(update.message.from_user.username + " has started conversation...")
        valid, user = utils.check_valid_chat(update)
        if valid:
            if user["is_active"]:
                tg_info = update.message.from_user
                context.user_data["username"] = tg_info.username
                context.user_data["user"] = tg_info.first_name
                context.user_data["user_id"] = tg_info.id
                context.user_data["is_admin"] = user["is_admin"]
                # logger.info("User " + tg_info.username + " started the conversation.")
                if context.user_data["is_admin"]:
                    keyboard = kb.ADMIN_MENU
                else:
                    keyboard = kb.MAIN_MENU
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "Hola " + tg_info.first_name + ", elije una opción:",
                    reply_markup=reply_markup,
                )
                return utils.MAIN_MENU
            else:
                await utils.reply_message(
                    update,
                    context,
                    "Para poder usar el bot, primero debes activar tu cuenta usando el comando /activate en un chat directo con el bot.",
                )
        else:
            if user["error"] == "api":
                await utils.reply_message(update, context, msgs.api_error)
            else:
                await utils.reply_message(update, context, msgs.forbidden)

    async def back(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        logger.info("Back")
        await query.answer()
        if context.user_data["is_admin"]:
            keyboard = kb.ADMIN_MENU
        else:
            keyboard = kb.MAIN_MENU
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Elije una opción:", reply_markup=reply_markup
        )
        return utils.MAIN_MENU

    async def end(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Returns `ConversationHandler.END`, which tells the
        ConversationHandler that the conversation is over.
        """
        logger.info("End conversation")
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Taluego!")
        return ConversationHandler.END

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data["error"] = "Meh"
        await update.message.reply_text(
            "Sorry '%s' is not a valid command" % update.message.text
        )

    async def unknown_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        context.user_data["error"] = "Meh"
        await update.message.reply_text(
            "Sorry I can't recognize you , you said '%s'" % update.message.text
        )

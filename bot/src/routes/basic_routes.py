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
    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info(update.message.from_user.username + " has started conversation...")
        valid, user = utils.check_valid_chat(update)
        if valid:
            if user["is_active"]:
                tg_info = update.message.from_user
                context.user_data["username"] = tg_info.username
                context.user_data["user"] = tg_info.first_name
                context.user_data["user_id"] = tg_info.id
                reply_markup = InlineKeyboardMarkup(kb.MAIN_MENU)
                await update.message.reply_text(
                    "Hola " + tg_info.first_name + ", elije una opción:",
                    reply_markup=reply_markup,
                )
                return utils.MAIN_MENU
            else:
                await utils.reply_message(
                    update,
                    context,
                    msgs.inactive,
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
        reply_markup = InlineKeyboardMarkup(kb.MAIN_MENU)
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

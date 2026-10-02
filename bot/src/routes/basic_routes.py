import utils.keyboard as kb
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
        """Only reached through utils.gate, which has already checked the chat and the account."""
        tg_info = update.message.from_user
        logger.info(context.user_data["app_user"]["username"] + " has started conversation...")
        reply_markup = InlineKeyboardMarkup(kb.MAIN_MENU)
        await update.message.reply_text(
            "Hola " + tg_info.first_name + ", elije una opción:",
            reply_markup=reply_markup,
        )
        return utils.MAIN_MENU

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

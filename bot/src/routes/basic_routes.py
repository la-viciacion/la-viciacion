import utils.keyboard as kb
import utils.messages as msgs
from telegram import InlineKeyboardMarkup, Update
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
        sent = await update.message.reply_text(
            "Hola " + tg_info.first_name + ", elije una opción:",
            reply_markup=reply_markup,
        )
        utils.remember_menu(context, update.message.chat.id, sent.message_id, tg_info.id)
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

    async def expired(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """A button the conversation no longer answers: its menu predates a restart or was opened by someone else.

        Only the person who pressed sees the notice (a popup): the message stays as it is, so in the group a
        bystander cannot spoil another player's menu. It must never raise: this is the end of the line."""
        try:
            await update.callback_query.answer(msgs.not_your_menu, show_alert=True)
        except Exception as e:  # e.g. Telegram refuses to answer a very old query
            logger.warning(f"Could not answer an expired button: {e}")

    async def end(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Returns `ConversationHandler.END`, which tells the
        ConversationHandler that the conversation is over.
        """
        logger.info("End conversation")
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Taluego!")
        return ConversationHandler.END

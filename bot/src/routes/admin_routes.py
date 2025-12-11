import requests
import telegram
import utils.keyboard as kb
import utils.messages as msgs
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.config import Config
from utils.my_utils import MyUtils
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

utils = MyUtils()
config = Config()


class AdminRoutes:

    async def send_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Send message option...")
        context.user_data["broadcast"] = ""
        query = update.callback_query
        if query.from_user.username in config.ADMIN_USERS:
            msg = "¿Qué quieres difundir a La Viciación? (/cancel para cancelar):"
            await utils.response_conversation(update, context, msg)
            return utils.SEND_MESSAGE

    async def send_message_action(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        # if update.message.from_user.username in config.ADMIN_USERS:
        message = update.message.text
        context.user_data["broadcast"] = message
        if message == "/cancel" or message.lower() == "cancel":
            await utils.response_conversation(update, context, "Send message canceled")
            return ConversationHandler.END
        else:
            keyboard = kb.YES_NO
            reply_markup = ReplyKeyboardMarkup(
                keyboard,
                one_time_keyboard=True,
                input_field_placeholder="¿Quieres confirmar los datos?",
                resize_keyboard=True,
                selective=True,
            )
            await update.message.reply_text(
                "¿Quieres enviar el siguiente mensaje?\n\n" + message,
                reply_markup=reply_markup,
            )
            return utils.SEND_MESSAGE

    async def send_message_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if "Sí" in str(update.message.text):
            message = str(context.user_data["broadcast"])
            await utils.bot.send_message(
                text=message,
                chat_id=config.TELEGRAM_GROUP_ID,
                parse_mode=telegram.constants.ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("Operación cancelada")
        await update.message.reply_text("Taluego!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

from telegram import Bot, Update
from telegram.ext import ContextTypes
from utils.config import Config
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


class ReadMessages:
    """_summary_"""

    def __init__(self, silent=None):
        self.bot = Bot(config.TELEGRAM_TOKEN)
        self.silent = silent
        # Conversation routes

    async def read_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        username = update.message.from_user.username
        name = update.message.from_user.first_name
        message = update.message.text
        logger.info(username+"("+name+")"+": "+message)
        # Implement here your action
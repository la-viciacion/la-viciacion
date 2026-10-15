import logging
import os
from logging.handlers import TimedRotatingFileHandler

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))
LOG_LEVEL = os.environ["BOT_LOG_LEVEL"]  # a level name: DEBUG, INFO, WARNING...


class LogManager:
    """The one logger of the service: to the console and to logs/log, a file a day, a week of them kept."""

    def __init__(self, log_dir="logs", log_level=LOG_LEVEL):
        os.makedirs(log_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        if self.logger.hasHandlers():
            return  # every module builds a LogManager: the handlers are added once
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "log"), when="midnight", interval=1, backupCount=7, encoding="utf-8"
        )
        file_handler.suffix = "%Y-%m-%d"
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        for handler in (file_handler, logging.StreamHandler()):
            handler.setLevel(log_level)
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def get_logger(self):
        return self.logger

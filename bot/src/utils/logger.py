import base64
import logging
import sys
import os
from logging.handlers import TimedRotatingFileHandler

from dotenv import dotenv_values

try:
    config = dotenv_values(".env")
    LOG_LEVEL = config["API_LOG_LEVEL"]
except Exception:
    LOG_LEVEL = os.environ["API_LOG_LEVEL"]

if LOG_LEVEL == "DEBUG":
    LOG_LEVEL = logging.DEBUG
elif LOG_LEVEL == "INFO":
    LOG_LEVEL = logging.INFO


class LogManager:

    def __init__(self, log_dir="logs", log_level=LOG_LEVEL):
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Crear el logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        # Evitar múltiples handlers duplicados
        if not self.logger.hasHandlers():
            # Crear un TimedRotatingFileHandler que rota el archivo a la medianoche
            file_handler = TimedRotatingFileHandler(
                filename=os.path.join(log_dir, "log"),
                when="midnight",  # Rotación diaria a medianoche
                interval=1,  # Cada día
                backupCount=7,  # Mantener un máximo de 7 archivos de log antiguos
                encoding="utf-8",
            )
            file_handler.suffix = "%Y-%m-%d"  # Añadir la fecha al nombre del archivo
            file_handler.setLevel(log_level)

            # Crear un StreamHandler para mostrar logs en la terminal
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)

            # Crear un formato de log
            formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)

            # Crear un formato de log
            formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)

            # Añadir los manejadores al logger
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)

    def debug(self, msg):
        self.logger.debug(msg)

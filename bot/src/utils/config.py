import json
import os

from dotenv import find_dotenv, load_dotenv


class Config:
    def __init__(self):
        # In Docker the variables come from env_file. For local development,
        # fall back to the shared .env at the repo root (never overrides os.environ).
        load_dotenv(find_dotenv(usecwd=True))

        self.ADMIN_USERS = json.loads(os.environ["ADMIN_USERS"])
        self.TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
        self.TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
        self.TELEGRAM_ADMIN_CHAT_ID = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
        self.API_URL = os.environ["API_URL"] + "/bot"
        self.API_KEY = os.environ["API_KEY"]
        self.SECRET_KEY = os.environ["SECRET_KEY"]
        self.ACCESS_TOKEN_EXPIRE_MINUTES = os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]
        self.SENTRY_URL = os.environ["SENTRY_URL_BOT"]
        self.ENVIRONMENT = os.environ["ENVIRONMENT"]
        self.OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

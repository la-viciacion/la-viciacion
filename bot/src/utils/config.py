import json
import logging
import os

from dotenv import dotenv_values


class Config:
    def __init__(self):
        try:
            # Load .env
            config = dotenv_values(".env")
            self.ADMIN_USERS = json.loads(config["ADMIN_USERS"])
            self.TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
            self.TELEGRAM_GROUP_ID = config["TELEGRAM_GROUP_ID"]
            self.TELEGRAM_ADMIN_CHAT_ID = config["TELEGRAM_ADMIN_CHAT_ID"]
            self.CLOCKIFY_BASEURL = config["CLOCKIFY_BASEURL"]
            self.CLOCKIFY_WORKSPACE = config["CLOCKIFY_WORKSPACE"]
            self.CLOCKIFY_ADMIN_API_KEY = config["CLOCKIFY_ADMIN_API_KEY"]
            self.API_URL = config["API_URL"] + "/bot"
            self.API_KEY = config["API_KEY"]
            self.SECRET_KEY = config["SECRET_KEY"]
            self.ACCESS_TOKEN_EXPIRE_MINUTES = config["ACCESS_TOKEN_EXPIRE_MINUTES"]
            self.SENTRY_URL = config["SENTRY_URL_BOT"]
            self.ENVIRONMENT = config["ENVIRONMENT"]
            self.OPENAI_API_KEY = config["OPENAI_API_KEY"]

        except Exception:
            self.TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
            self.ADMIN_USERS = json.loads(os.environ["ADMIN_USERS"])
            self.TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
            self.TELEGRAM_ADMIN_CHAT_ID = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
            self.CLOCKIFY_BASEURL = os.environ["CLOCKIFY_BASEURL"]
            self.CLOCKIFY_WORKSPACE = os.environ["CLOCKIFY_WORKSPACE"]
            self.CLOCKIFY_ADMIN_API_KEY = os.environ["CLOCKIFY_ADMIN_API_KEY"]
            self.API_URL = os.environ["API_URL"] + "/bot"
            self.API_KEY = os.environ["API_KEY"]
            self.SECRET_KEY = os.environ["SECRET_KEY"]
            self.ACCESS_TOKEN_EXPIRE_MINUTES = os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]
            self.SENTRY_URL = os.environ["SENTRY_URL_BOT"]
            self.ENVIRONMENT = os.environ["ENVIRONMENT"]
            self.OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

import datetime
import json
import os

from dotenv import dotenv_values


class Config:
    def __init__(self):
        try:
            # Load .env
            config = dotenv_values(".env")
            self.ADMIN_USERS = json.loads(config["ADMIN_USERS"])
            self.DEFAULT_ADMIN_PASS = config["DEFAULT_ADMIN_PASS"]
            self.TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
            self.TELEGRAM_GROUP_ID = config["TELEGRAM_GROUP_ID"]
            self.TELEGRAM_ADMIN_CHAT_ID = config["TELEGRAM_ADMIN_CHAT_ID"]
            self.DB_HOST = config["MARIADB_HOST"]
            self.DB_NAME = config["MARIADB_DATABASE"]
            self.DB_USER = config["MARIADB_USER"]
            self.DB_PASS = config["MARIADB_PASSWORD"]
            self.CLOCKIFY_BASEURL = config["CLOCKIFY_BASEURL"]
            self.CLOCKIFY_WORKSPACE = config["CLOCKIFY_WORKSPACE"]
            self.CLOCKIFY_ADMIN_API_KEY = config["CLOCKIFY_ADMIN_API_KEY"]
            self.RAWG_URL = config["RAWG_URL"]
            self.INITIAL_DATE = config["INITIAL_DATE"]
            self.INVITATION_KEY = config["INVITATION_KEY"]
            self.API_KEY = config["API_KEY"]
            self.SECRET_KEY = config["SECRET_KEY"]
            self.ACCESS_TOKEN_EXPIRE_MINUTES = config["ACCESS_TOKEN_EXPIRE_MINUTES"]
            self.CORS_ORIGINS = json.loads(config["CORS_ORIGINS"])
            self.SMTP_HOST = config["SMTP_HOST"]
            self.SMTP_PORT = config["SMTP_PORT"]
            self.SMTP_EMAIL = config["SMTP_EMAIL"]
            self.SMTP_USER = config["SMTP_USER"]
            self.SMTP_PASS = config["SMTP_PASS"]
            self.SENTRY_URL = config["SENTRY_URL_API"]
            self.ENVIRONMENT = config["ENVIRONMENT"]
            self.OPENAI_API_KEY = config["OPENAI_API_KEY"]
            self.OPENAI_MODEL = config["OPENAI_MODEL"]
            self.SYNC_DAYS = int(config["SYNC_DAYS"])
            self.CLOCKIFY_SIGNATURES = json.loads(config["CLOCKIFY_SIGNATURES"])

        except Exception:
            self.TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
            self.ADMIN_USERS = json.loads(os.environ["ADMIN_USERS"])
            self.DEFAULT_ADMIN_PASS = os.environ["DEFAULT_ADMIN_PASS"]
            self.TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
            self.TELEGRAM_ADMIN_CHAT_ID = os.environ["TELEGRAM_ADMIN_CHAT_ID"]
            self.DB_HOST = os.environ["MARIADB_HOST"]
            self.DB_NAME = os.environ["MARIADB_DATABASE"]
            self.DB_USER = os.environ["MARIADB_USER"]
            self.DB_PASS = os.environ["MARIADB_PASSWORD"]
            self.CLOCKIFY_BASEURL = os.environ["CLOCKIFY_BASEURL"]
            self.CLOCKIFY_WORKSPACE = os.environ["CLOCKIFY_WORKSPACE"]
            self.CLOCKIFY_ADMIN_API_KEY = os.environ["CLOCKIFY_ADMIN_API_KEY"]
            self.RAWG_URL = os.environ["RAWG_URL"]
            self.INITIAL_DATE = os.environ["INITIAL_DATE"]
            self.INVITATION_KEY = os.environ["INVITATION_KEY"]
            self.API_KEY = os.environ["API_KEY"]
            self.SECRET_KEY = os.environ["SECRET_KEY"]
            self.ACCESS_TOKEN_EXPIRE_MINUTES = os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]
            self.CORS_ORIGINS = json.loads(os.environ["CORS_ORIGINS"])
            self.SMTP_HOST = os.environ["SMTP_HOST"]
            self.SMTP_PORT = os.environ["SMTP_PORT"]
            self.SMTP_EMAIL = os.environ["SMTP_EMAIL"]
            self.SMTP_USER = os.environ["SMTP_USER"]
            self.SMTP_PASS = os.environ["SMTP_PASS"]
            self.SENTRY_URL = os.environ["SENTRY_URL_API"]
            self.ENVIRONMENT = os.environ["ENVIRONMENT"]
            self.OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
            self.OPENAI_MODEL = os.environ["OPENAI_MODEL"]
            self.SYNC_DAYS = int(os.environ["SYNC_DAYS"])
            self.CLOCKIFY_SIGNATURES = json.loads(os.environ["CLOCKIFY_SIGNATURES"])

        self.CURRENT_SEASON = datetime.datetime.now().year

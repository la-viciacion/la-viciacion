import datetime
import json
import os
from typing import Any

from dotenv import dotenv_values


class Config:
    def __init__(self):
        # Load variables from .env file as fallback
        # In Docker, os.environ will already have the variables (from env_file)
        # In local development, .env will be used
        self._dotenv_config = dotenv_values(".env")
        
        # Telegram
        self.TELEGRAM_TOKEN = self._get_env("TELEGRAM_TOKEN")
        self.TELEGRAM_GROUP_ID = self._get_env("TELEGRAM_GROUP_ID")
        self.TELEGRAM_ADMIN_CHAT_ID = self._get_env("TELEGRAM_ADMIN_CHAT_ID")
        
        # Admin
        self.ADMIN_USERS = self._get_env_json("ADMIN_USERS")
        self.DEFAULT_ADMIN_PASS = self._get_env("DEFAULT_ADMIN_PASS")
        
        # Database
        self.DB_HOST = self._get_env("MARIADB_HOST")
        self.DB_NAME = self._get_env("MARIADB_DATABASE")
        self.DB_USER = self._get_env("MARIADB_USER")
        self.DB_PASS = self._get_env("MARIADB_PASSWORD")
        
        # Clockify
        self.CLOCKIFY_BASEURL = self._get_env("CLOCKIFY_BASEURL")
        self.CLOCKIFY_WORKSPACE = self._get_env("CLOCKIFY_WORKSPACE")
        self.CLOCKIFY_ADMIN_API_KEY = self._get_env("CLOCKIFY_ADMIN_API_KEY")
        self.CLOCKIFY_SIGNATURES = self._get_env_json("CLOCKIFY_SIGNATURES")
        
        # External APIs
        self.RAWG_URL = self._get_env("RAWG_URL")
        self.OPENAI_API_KEY = self._get_env("OPENAI_API_KEY")
        self.OPENAI_MODEL = self._get_env("OPENAI_MODEL")
        
        # Security
        self.INVITATION_KEY = self._get_env("INVITATION_KEY")
        self.API_KEY = self._get_env("API_KEY")
        self.SECRET_KEY = self._get_env("SECRET_KEY")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = self._get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
        
        # CORS
        self.CORS_ORIGINS = self._get_env_json("CORS_ORIGINS")
        
        # SMTP
        self.SMTP_HOST = self._get_env("SMTP_HOST")
        self.SMTP_PORT = self._get_env("SMTP_PORT")
        self.SMTP_EMAIL = self._get_env("SMTP_EMAIL")
        self.SMTP_USER = self._get_env("SMTP_USER")
        self.SMTP_PASS = self._get_env("SMTP_PASS")
        
        # Monitoring
        self.SENTRY_URL = self._get_env("SENTRY_URL_API")
        self.ENVIRONMENT = self._get_env("ENVIRONMENT")
        
        # App Config
        self.INITIAL_DATE = self._get_env("INITIAL_DATE")
        self.SYNC_DAYS = int(self._get_env("SYNC_DAYS"))
        self.CURRENT_SEASON = datetime.datetime.now().year
    
    def _get_env(self, key: str) -> str:
        """
        Gets an environment variable.
        Priority: os.environ (Docker) > .env (local development)
        """
        value = os.getenv(key) or self._dotenv_config.get(key)
        if value is None:
            raise ValueError(f"Environment variable '{key}' not found")
        return value
    
    def _get_env_json(self, key: str) -> Any:
        """
        Gets an environment variable and parses it as JSON.
        """
        return json.loads(self._get_env(key))

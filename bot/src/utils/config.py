import logging
import os
import threading

import requests
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger("bot.config")


class Config:
    """Bot configuration (a singleton: every module asks for it).

    The bot is read-only: it logs into the API as the superadmin ("admin" with
    GOD_ADMIN_PASS) and only uses the generic endpoints. The Telegram token and
    chats come from the TELEGRAM_* variables of .env and nowhere else: the API does
    not store them, so a copy of its database cannot run the bot.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = False
            return cls._instance

    def __init__(self):
        with self._lock:
            if self._ready:
                return
            # In Docker the variables come from env_file. For local development,
            # fall back to the shared .env at the repo root (never overrides os.environ).
            load_dotenv(find_dotenv(usecwd=True))

            self.API_URL = os.environ["API_URL"]
            self.API_USER = "admin"
            self.API_PASSWORD = os.environ["GOD_ADMIN_PASS"]
            self.SENTRY_URL = os.environ["SENTRY_URL_BOT"]
            self.ENVIRONMENT = os.environ["ENVIRONMENT"]

            self.TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
            self.TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
            self.TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or None
            self._ready = True

    def login(self) -> None:
        """Get a fresh superadmin token from the API."""
        response = requests.post(
            f"{self.API_URL}/token",
            data={"username": self.API_USER, "password": self.API_PASSWORD},
            timeout=10,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Authenticated request; logs in on first use and again if the token expired."""
        kwargs.setdefault("timeout", 10)
        for attempt in (1, 2):
            if not getattr(self, "_token", None):
                self.login()
            headers = {"Authorization": f"Bearer {self._token}"}
            response = requests.request(method, url, headers=headers, **kwargs)
            if response.status_code != 401 or attempt == 2:
                return response
            self._token = None

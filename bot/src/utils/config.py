import logging
import os
import threading
import time

import requests
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger("bot.config")

WATCH_SECONDS = 60


class Config:
    """Bot configuration (a singleton: every module asks for it).

    The bot is read-only: it logs into the API as the superadmin ("admin" with
    GOD_ADMIN_PASS) and only uses the generic endpoints. The Telegram token and
    chats are edited from the admin panel and served by the API
    (GET /manage/settings/telegram); the bot restarts itself when they change so
    it picks them up (Docker's restart policy brings it back). The TELEGRAM_*
    variables of .env are only a fallback if the API has nothing yet.
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

            self._load_telegram()
            self._ready = True
            threading.Thread(target=self._watch, name="settings-watch", daemon=True).start()

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

    def _fetch(self) -> dict:
        response = self.request("GET", f"{self.API_URL}/manage/settings/telegram")
        response.raise_for_status()
        return response.json()

    def _load_telegram(self) -> None:
        """Block until the API gives (or the environment has) a token and a group."""
        while True:
            values = {}
            try:
                values = self._fetch()
            except Exception as e:
                logger.warning("API settings not available yet: %s", e)
            token = values.get("token") or os.getenv("TELEGRAM_TOKEN")
            group = values.get("group_id") or os.getenv("TELEGRAM_GROUP_ID")
            if token and group:
                self.TELEGRAM_TOKEN = token
                self.TELEGRAM_GROUP_ID = group
                self.TELEGRAM_ADMIN_CHAT_ID = values.get("admin_chat_id") or os.getenv("TELEGRAM_ADMIN_CHAT_ID")
                self._version = values.get("version")
                return
            logger.warning("Telegram token/group not configured yet; retrying in 15s")
            time.sleep(15)

    def _watch(self) -> None:
        while True:
            time.sleep(WATCH_SECONDS)
            try:
                version = self._fetch().get("version")
            except Exception:
                continue  # the API may be restarting
            if version != self._version:
                logger.warning("Telegram settings changed: restarting to apply them")
                os._exit(0)

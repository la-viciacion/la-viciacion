import json
import os
from typing import Any

from dotenv import find_dotenv, load_dotenv


class Config:
    def __init__(self):
        # In Docker the variables come from env_file. For local development,
        # fall back to the shared .env at the repo root (never overrides os.environ).
        load_dotenv(find_dotenv(usecwd=True))

        # The keys of outside services are read from the environment every time and never stored (see
        # utils/settings.py, `env_only`): the Telegram token and chats (TELEGRAM_TOKEN / TELEGRAM_GROUP_ID /
        # TELEGRAM_ADMIN_CHAT_ID) and the keys and default models of each AI provider (OPENAI_AI_API_KEY,
        # OPENAI_AI_MODEL, OPENAI_CHAT_AI_MODEL, and the same for GOOGLE, ANTHROPIC and OPENROUTER; utils/ai_providers.py): there is no default for a model in the code, and
        # no variable says which provider to use (the admin picks among those that have a key).

        # Admin
        self.GOD_ADMIN_PASS = self._get_env("GOD_ADMIN_PASS")
        
        # Database
        self.DB_HOST = self._get_env("MARIADB_HOST")
        self.DB_NAME = self._get_env("MARIADB_DATABASE")
        self.DB_USER = self._get_env("MARIADB_USER")
        self.DB_PASS = self._get_env("MARIADB_PASSWORD")
        
        # Security
        self.SECRET_KEY = self._get_env("SECRET_KEY")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = self._get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
        
        # CORS
        self.CORS_ORIGINS = self._get_env_json("CORS_ORIGINS")
        
        # Outgoing mail (password recovery). Optional: without SMTP_HOST, SMTP_EMAIL and
        # PUBLIC_URL the feature is off and the API answers "not configured".
        self.SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
        self.SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
        self.SMTP_EMAIL = os.getenv("SMTP_EMAIL", "").strip()  # the From address
        self.SMTP_USER = os.getenv("SMTP_USER", "").strip() or self.SMTP_EMAIL
        self.SMTP_PASS = os.getenv("SMTP_PASS", "")
        self.SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").strip().lower()  # starttls | ssl | none (local testing)
        # Where the app is reached from outside (the recovery link points there), e.g. https://lavi.example.com
        self.PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

        # Interactive API docs (Swagger/ReDoc/openapi.json): off unless asked for
        self.API_DOCS_ENABLED = os.getenv("API_DOCS_ENABLED", "false").strip().lower() in ("1", "true", "yes")

        # Monitoring
        self.SENTRY_URL = self._get_env("SENTRY_URL_API")
        self.ENVIRONMENT = self._get_env("ENVIRONMENT")
        
    
    def _get_env(self, key: str) -> str:
        """
        Gets an environment variable.
        Priority: os.environ (Docker) > .env (local development)
        """
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"Environment variable '{key}' not found")
        return value
    
    def _get_env_json(self, key: str) -> Any:
        """
        Gets an environment variable and parses it as JSON.
        """
        return json.loads(self._get_env(key))

    @property
    def MAIL_ENABLED(self) -> bool:
        """Can the API send the recovery email? (SMTP server, sender and the public address of the app)"""
        return bool(self.SMTP_HOST and self.SMTP_EMAIL and self.PUBLIC_URL)

    @property
    def APP_VERSION(self) -> str:
        """The release tag, baked into the image at build time (release.yml); `dev` when built from a checkout."""
        return os.getenv("APP_VERSION", "").strip() or "dev"

    @property
    def RAWG_API_KEY(self) -> str:
        return os.getenv("RAWG_API_KEY", "").strip()

    @property
    def TWITCH_CLIENT_ID(self) -> str:
        return os.getenv("TWITCH_CLIENT_ID", "").strip()

    @property
    def TWITCH_CLIENT_SECRET(self) -> str:
        return os.getenv("TWITCH_CLIENT_SECRET", "").strip()

    @property
    def HETZNER_API_TOKEN(self) -> str:
        return os.getenv("HETZNER_API_TOKEN", "").strip()

    @property
    def PROMETHEUS_URL(self) -> str:
        return os.getenv("PROMETHEUS_URL", "").strip().rstrip("/")

    @property
    def HETZNER_SERVER_ID(self) -> str:
        return os.getenv("HETZNER_SERVER_ID", "").strip()

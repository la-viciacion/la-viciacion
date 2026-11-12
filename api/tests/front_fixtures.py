"""The answers of the real API that the front's tests load, so a field the API drops cannot go unnoticed in the panel.

`GET /manage/settings` is built here by the route itself (on an in-memory database, with the environment of each scenario), and
saved in `front/tests/fixtures/`. `tests/test_front_fixtures.py` fails when the files are out of date; regenerate them with

    cd api && python -m tests.front_fixtures
"""
import json
import os
import types
from pathlib import Path
from unittest import mock

from fastapi.encoders import jsonable_encoder

from src.routers.manage import system
from src.utils import email as mail
from src.utils import settings
from tests.sqlite_db import make_session

TARGET = Path(__file__).resolve().parents[2] / "front" / "tests" / "fixtures"
AI_VARIABLES = ("OPENAI_AI_API_KEY", "OPENAI_AI_MODEL", "OPENAI_CHAT_AI_MODEL", "GOOGLE_AI_API_KEY", "GOOGLE_AI_MODEL", "GOOGLE_CHAT_AI_MODEL", "OPENAI_ADMIN_KEY")

# Environments the panel must open in: both providers set up, and an .env with nothing of the AI
SCENARIOS = {
    "manage-settings.full.json": {
        "OPENAI_AI_API_KEY": "sk-test", "OPENAI_AI_MODEL": "gpt-test", "GOOGLE_AI_API_KEY": "g-test", "GOOGLE_AI_MODEL": "gemini-test",
        "OPENAI_ADMIN_KEY": "sk-admin", "TELEGRAM_TOKEN": "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345", "TELEGRAM_GROUP_ID": "-100",
    },
    "manage-settings.empty.json": {},
}


def build(env: dict) -> dict:
    db = make_session()
    clean = {key: value for key, value in os.environ.items() if key not in AI_VARIABLES and not key.startswith("TELEGRAM_")}
    with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
        stored = settings.get_all(db)
        with mock.patch.object(settings, "get", side_effect=lambda key: stored[key]), \
                mock.patch.object(mail, "status", return_value={"configured": False, "missing": ["SMTP_HOST"], "host": "", "port": 587, "security": "starttls", "from": "", "public_url": ""}):
            return jsonable_encoder(system.get_settings(types.SimpleNamespace(email=None), db))


def render(payload: dict) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, env in SCENARIOS.items():
        (TARGET / name).write_text(render(build(env)), encoding="utf-8", newline="\n")
        print("written", TARGET / name)


if __name__ == "__main__":
    main()

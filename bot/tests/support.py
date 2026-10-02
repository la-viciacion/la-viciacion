"""What the bot's tests need before they can import it, and stand-ins for Telegram's objects.

The bot reads its settings when its modules are imported (`Config()` is a singleton created at import), and its
modules import each other by top-level names (`utils.keyboard`, `routes.my_routes`): it runs with `src/` as the
working directory. Importing this module first sets the environment and the path, so a test can then
`import utils.my_utils` like the application does. Nothing here reaches the network: the API address points at a
closed port and the Telegram settings come from the environment fallback.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
os.environ.setdefault("API_URL", "http://127.0.0.1:9/api/v1")  # a closed port: any real request fails at once
os.environ.setdefault("GOD_ADMIN_PASS", "test-admin-pass")
os.environ.setdefault("SENTRY_URL_BOT", "")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("BOT_LOG_LEVEL", "INFO")
os.environ.setdefault("TELEGRAM_TOKEN", "123456789:" + "A" * 30)
os.environ.setdefault("TELEGRAM_GROUP_ID", "-1001234567890")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GROUP_ID = int(os.environ["TELEGRAM_GROUP_ID"])


def user(telegram_id=111, username="ana", name="Ana", is_active=1, user_id=1, **extra):
    """An account as GET /users/ returns it."""
    return {"id": user_id, "username": username, "name": name, "telegram_id": telegram_id, "is_active": is_active, **extra}


def make_update(text=None, chat_type="private", chat_id=111, sender_id=111, is_bot=False, username="ana", first_name="Ana", callback=False):
    """A Telegram update with an async `reply_text` and, for callbacks, a query with async `answer`/`edit_message_text`."""
    sender = SimpleNamespace(id=sender_id, is_bot=is_bot, username=username, first_name=first_name)
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    message = None
    query = None
    if callback:
        query = SimpleNamespace(answer=mock.AsyncMock(), edit_message_text=mock.AsyncMock())
    else:
        message = SimpleNamespace(text=text, chat=chat, from_user=sender, reply_text=mock.AsyncMock())
    return SimpleNamespace(effective_chat=chat, effective_user=sender, message=message, callback_query=query)


def make_context(app_user=None, bot_username="LaViciacionBot"):
    return SimpleNamespace(bot=SimpleNamespace(username=bot_username), user_data={"app_user": app_user} if app_user else {}, error=None)

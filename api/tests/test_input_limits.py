import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src import auth
from src.database import schemas
from src.routers import manage, timers
from src.routers import users as users_router

USER = types.SimpleNamespace(id=1, username="ana", is_admin=1, is_active=1)
NOW = "2026-03-01T10:00:00"
LATER = "2026-03-01T11:00:00"


class NotesLengthTests(unittest.TestCase):
    def test_notes_longer_than_the_column_are_refused_everywhere(self):
        long = "x" * (schemas.NOTES_MAX + 1)
        for build in (
            lambda: schemas.GameTimerCreate(user_id=1, game_id="g", notes=long),
            lambda: schemas.ManualSessionCreate(game_id="g", platform="pc", start_time=NOW, end_time=LATER, notes=long),
            lambda: schemas.SessionUpdate(notes=long),
            lambda: manage.TimerCreate(user_id=1, game_id="g", start_time=NOW, end_time=LATER, notes=long),
            lambda: manage.TimerPatch(notes=long),
        ):
            with self.assertRaises(ValidationError):
                build()

    def test_notes_of_the_maximum_length_are_fine(self):
        self.assertEqual(len(schemas.SessionUpdate(notes="x" * schemas.NOTES_MAX).notes), schemas.NOTES_MAX)


class ListLimitTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(timers.router)
        app.include_router(users_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: USER
        app.dependency_overrides[timers.get_db] = lambda: mock.MagicMock()
        app.dependency_overrides[users_router.get_db] = lambda: mock.MagicMock()
        self.client = TestClient(app)

    def test_history_limit_must_be_between_1_and_500(self):
        for limit in ("0", "-1", "501", "1000000"):
            self.assertEqual(self.client.get("/timers/history/1", params={"limit": limit}).status_code, 422, limit)

    def test_history_accepts_a_sane_limit(self):
        with mock.patch.object(timers, "get_timer_history", return_value=[]) as history:
            self.assertEqual(self.client.get("/timers/history/1", params={"limit": "500"}).status_code, 200)
        self.assertEqual(history.call_args.args[3], 500)


if __name__ == "__main__":
    unittest.main()

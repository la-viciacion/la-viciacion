import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from src import auth
from src.routers import users as users_router
from src.utils import messages as msg

USER = types.SimpleNamespace(id=1, username="ana", is_admin=0, is_active=1)


class LegacyGameEndpointTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(users_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: USER
        app.dependency_overrides[users_router.get_db] = lambda: mock.MagicMock()
        self.client = TestClient(app)
        for name, value in {
            "get_user_by_username": USER,
            "get_game_by_id": None,
        }.items():
            patcher = mock.patch.object(users_router.users, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_adding_an_unknown_game_is_a_404_not_a_500(self):
        with mock.patch.object(users_router.games, "get_game_by_id", return_value=None):
            r = self.client.post("/users/ana/new_game", json={"game_id": "nope", "platform": "pc"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"], msg.GAME_NOT_FOUND)

    def test_a_database_error_does_not_leak_its_text(self):
        with mock.patch.object(users_router.games, "get_game_by_id", return_value=object()), \
                mock.patch.object(users_router.users, "add_new_game", side_effect=SQLAlchemyError("secret table detail")):
            r = self.client.post("/users/ana/new_game", json={"game_id": "g", "platform": "pc"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json()["detail"], msg.INTERNAL_ERROR)

    def test_completing_reports_a_database_error_generically(self):
        entry = types.SimpleNamespace(completed=0)
        with mock.patch.object(users_router.users, "get_game_by_id", return_value=entry), \
                mock.patch.object(users_router.users, "complete_game", side_effect=SQLAlchemyError("secret")):
            r = self.client.patch("/users/ana/complete-game", params={"game_id": "g"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json()["detail"], msg.INTERNAL_ERROR)

    def test_a_score_outside_0_to_10_is_refused(self):
        for score in ("-1", "10.5", "nan", "1e9"):
            r = self.client.patch("/users/ana/rate-game", params={"game_id": "g", "score": score})
            self.assertEqual(r.status_code, 422, score)

    def test_a_valid_score_is_saved(self):
        entry = types.SimpleNamespace(id=1, game_id="g", score=None)
        with mock.patch.object(users_router.users, "get_game_by_id", return_value=entry), \
                mock.patch.object(users_router.users, "rate_game", new=mock.AsyncMock(return_value={"score": 7.5})) as rate:
            r = self.client.patch("/users/ana/rate-game", params={"game_id": "g", "score": "7.5"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rate.await_args.args[3], 7.5)


if __name__ == "__main__":
    unittest.main()

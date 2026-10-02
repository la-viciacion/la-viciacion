import datetime
import io
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from src import auth
from src.database import models, schemas
from src.routers import users as users_router
from src.utils import my_utils
from tests.sqlite_db import make_session

USER = types.SimpleNamespace(id=1, username="ana", is_admin=0, is_active=1)


class CompletionFlowTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(users_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: USER
        app.dependency_overrides[users_router.get_db] = lambda: mock.MagicMock()
        self.client = TestClient(app)
        self.entry = types.SimpleNamespace(id=7, season=datetime.date.today().year, completed=0, game_id="g", started_date=None)
        patches = {
            "get_user_by_username": USER,
            "get_library_entry": self.entry,
            "completed_in_season": False,
            "get_library_item": {"id": 7, "completed": True},
        }
        for name, value in patches.items():
            p = mock.patch.object(users_router.users, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_completing_answers_before_the_slow_follow_ups_and_schedules_them(self):
        with mock.patch.object(users_router.users, "complete_entry") as complete, \
                mock.patch.object(users_router.actions, "after_completion") as after:
            r = self.client.patch("/users/ana/library/7/completion", json={"completed": True}, params={"silent": "true"})
        self.assertEqual(r.status_code, 200)
        complete.assert_called_once()
        after.assert_called_once_with(7, True)  # entry id, silent: run in the background

    def test_the_route_is_a_plain_function(self):
        import inspect

        self.assertFalse(inspect.iscoroutinefunction(users_router.update_completion))

    def test_changing_only_the_date_schedules_nothing(self):
        self.entry.completed = 1
        with mock.patch.object(users_router.users, "set_completed_date"), \
                mock.patch.object(users_router.actions, "after_completion") as after:
            r = self.client.patch(
                "/users/ana/library/7/completion",
                json={"completed": True, "completed_date": datetime.date.today().isoformat()},
            )
        self.assertEqual(r.status_code, 200)
        after.assert_not_called()


class AvatarUploadTests(unittest.TestCase):
    def test_an_avatar_is_read_and_stored_by_a_plain_route(self):
        app = FastAPI()
        app.include_router(users_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: USER
        app.dependency_overrides[users_router.get_db] = lambda: mock.MagicMock()
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
        with mock.patch.object(users_router.users, "get_user_by_username", return_value=USER), \
                mock.patch.object(users_router.users, "upload_avatar") as store:
            r = TestClient(app).patch("/users/ana/avatar", files={"file": ("a.png", buffer.getvalue(), "image/png")})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(store.call_args.args[2][:4], b"\x89PNG")


class MarkExistingGamesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Game(id="g1", name="Doom", slug="doom", rawg_id=100),
            models.Game(id="g2", name="Quake", slug="quake-1996", rawg_id=None),
            models.Game(id="g3", name="Hades", slug=None, rawg_id=None),
        ])
        self.db.commit()

    def candidate(self, name, slug="", rawg_id=None):
        return schemas.RawgGameCandidate(rawg_id=rawg_id or 0, name=name, slug=slug)

    def test_a_candidate_matches_by_rawg_id_slug_or_name(self):
        candidates = [
            self.candidate("Anything", rawg_id=100),
            self.candidate("Other", slug="quake-1996"),
            self.candidate("Hades"),
            self.candidate("Not in the db", slug="nope", rawg_id=999),
        ]
        my_utils.mark_existing_games(self.db, candidates)
        self.assertEqual([(c.exists_in_db, c.db_game_id) for c in candidates],
                         [(True, "g1"), (True, "g2"), (True, "g3"), (False, None)])

    def test_it_asks_the_database_once_however_many_candidates_there_are(self):
        from sqlalchemy import event

        queries = []
        event.listen(self.db.get_bind(), "before_cursor_execute", lambda *a: queries.append(a[2]))
        my_utils.mark_existing_games(self.db, [self.candidate(f"Game {i}", slug=f"g{i}", rawg_id=i + 1) for i in range(10)])
        self.assertEqual(len(queries), 1)

    def test_no_candidates_no_query(self):
        my_utils.mark_existing_games(mock.MagicMock(), [])


if __name__ == "__main__":
    unittest.main()

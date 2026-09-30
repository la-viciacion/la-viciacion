import asyncio
import datetime
import inspect
import threading
import types
import unittest
from unittest import mock

from src import auth
from src.database.schemas import GameTimerCreate
from src.routers import timers
from src.utils import actions, my_utils


class OffTheLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_openai_call_runs_in_a_worker_thread(self):
        seen = []

        def completion(**kwargs):
            seen.append(threading.current_thread())
            return None

        values = {"notifications.enabled": True, "telegram.token": None, "telegram.group_id": None}
        with mock.patch.object(my_utils.oai_client, "chat_completion", completion), \
                mock.patch.object(my_utils.settings, "get", side_effect=values.get), \
                mock.patch.object(my_utils.push, "is_ready", return_value=True), \
                mock.patch.object(my_utils.push, "notify_group", new=mock.AsyncMock()):
            await my_utils.send_message("hola", False, openai=True)
        self.assertEqual(len(seen), 1)
        self.assertIsNot(seen[0], threading.main_thread())

    async def test_http_requests_run_in_a_worker_thread(self):
        seen = []

        def get(url, params, timeout):
            seen.append(threading.current_thread())
            return "response"

        with mock.patch.object(my_utils.requests, "get", get):
            self.assertEqual(await my_utils._http_get("u", {}, timeout=1), "response")
        self.assertIsNot(seen[0], threading.main_thread())

    def test_the_auth_dependency_is_not_a_coroutine(self):
        self.assertFalse(inspect.iscoroutinefunction(auth.get_current_user))


class StartTimerTests(unittest.TestCase):
    def db(self, entry_exists, season_entry_exists):
        db = mock.MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.scalar.return_value = None
        db.query.return_value.filter_by.return_value.first.side_effect = [
            object() if entry_exists else None,
            object() if season_entry_exists else None,
        ]
        return db

    def start(self, db):
        body = GameTimerCreate(user_id=1, game_id="g", platform="pc")
        add = mock.MagicMock()
        with mock.patch.object(timers, "check_new_timer"),                 mock.patch.object(timers.users_crud, "get_user_by_id", return_value=object()),                 mock.patch.object(timers.users_crud, "add_new_game", add):
            _, announce = timers.create_timer(db, body)
        return announce, add

    def test_starting_a_timer_is_plain_database_work(self):
        # nothing in it waits for the network any more: the notice goes to a background task
        self.assertFalse(inspect.iscoroutinefunction(timers.create_timer))
        self.assertFalse(inspect.iscoroutinefunction(timers.start_timer))

    def test_the_first_time_in_a_season_is_announced_but_not_here(self):
        announce, add = self.start(self.db(entry_exists=False, season_entry_exists=False))
        self.assertTrue(announce)
        add.assert_called_once()

    def test_the_same_game_on_another_platform_is_not_announced(self):
        announce, add = self.start(self.db(entry_exists=False, season_entry_exists=True))
        self.assertFalse(announce)
        add.assert_called_once()

    def test_a_known_entry_is_neither_created_nor_announced(self):
        announce, add = self.start(self.db(entry_exists=True, season_entry_exists=True))
        self.assertFalse(announce)
        add.assert_not_called()


class AfterTimerStartTests(unittest.TestCase):
    def run_after(self, new_game_id):
        announce = mock.AsyncMock()
        db = mock.MagicMock()
        patches = [
            mock.patch("src.database.database.SessionLocal", return_value=db),
            mock.patch.object(actions.achievements, "populate_achievements"),
            mock.patch.object(actions.achievements, "timer_started", new=mock.AsyncMock()),
            mock.patch.object(actions.achievements, "user_played_total_games", new=mock.AsyncMock()),
            mock.patch.object(actions.achievements, "teamwork", new=mock.AsyncMock()),
            mock.patch.object(actions.users, "get_user_by_id", return_value=types.SimpleNamespace(id=1)),
            mock.patch.object(actions.games, "get_game_by_id", return_value=types.SimpleNamespace(id="g")),
            mock.patch.object(actions.users, "announce_new_game", announce),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        actions.after_timer_start(1, datetime.datetime(2026, 3, 1, 10, 0), new_game_id)
        return announce

    def test_a_new_game_is_announced_in_the_background(self):
        self.assertEqual(self.run_after("g").await_count, 1)

    def test_nothing_is_announced_otherwise(self):
        self.assertEqual(self.run_after(None).await_count, 0)


class AfterCompletionTests(unittest.TestCase):
    def run_after(self, entry):
        follow_up = mock.AsyncMock()
        db = mock.MagicMock()
        db.get.return_value = entry
        with mock.patch("src.database.database.SessionLocal", return_value=db),                 mock.patch.object(actions.users, "after_completion", follow_up):
            actions.after_completion(7, silent=True)
        return follow_up, db

    def test_the_follow_ups_run_with_their_own_session_and_close_it(self):
        entry = object()
        follow_up, db = self.run_after(entry)
        follow_up.assert_awaited_once_with(db, entry, True)
        db.close.assert_called_once()

    def test_an_entry_that_vanished_is_ignored(self):
        follow_up, _ = self.run_after(None)
        follow_up.assert_not_awaited()

    def test_a_failure_is_logged_not_raised(self):
        with mock.patch("src.database.database.SessionLocal", return_value=mock.MagicMock()),                 mock.patch.object(actions.users, "after_completion", side_effect=RuntimeError("boom")):
            actions.after_completion(7)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch

from src.database.schemas import GameTimerCreate
from src.crud import timers


def db_where_exist(*models):
    """A db whose `query(Model.id)` finds a row only for the given models."""
    db = MagicMock()

    def query(column):
        q = MagicMock()
        q.filter.return_value.first.return_value = object() if column.class_ in models else None
        return q

    db.query.side_effect = query
    return db


def body(**kw):
    return GameTimerCreate(**{"user_id": 1, "game_id": "g1", "platform": None, **kw})


class CheckNewTimerTests(unittest.TestCase):
    def test_an_unknown_game_is_refused(self):
        with self.assertRaises(timers.Refused) as ctx:
            timers.check_new_timer(db_where_exist(timers.User), body())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_an_unknown_user_is_refused(self):
        with self.assertRaises(timers.Refused) as ctx:
            timers.check_new_timer(db_where_exist(timers.Game), body())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_an_unknown_platform_is_refused(self):
        with self.assertRaises(timers.Refused) as ctx:
            timers.check_new_timer(db_where_exist(timers.User, timers.Game), body(platform="nope"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_a_known_game_without_platform_passes(self):
        timers.check_new_timer(db_where_exist(timers.User, timers.Game), body())

    def test_a_known_platform_passes(self):
        timers.check_new_timer(db_where_exist(timers.User, timers.Game, timers.PlatformTag), body(platform="pc"))


class OneTimerAtATimeTests(unittest.TestCase):
    """Two starts of the same user (two taps, two devices) must not both pass the "no running timer" check."""

    def test_the_lock_is_a_locking_read_of_the_user_row(self):
        db = MagicMock()
        timers.lock_sessions(db, 7)
        db.query.return_value.filter.return_value.with_for_update.assert_called_once_with()

    def test_starting_locks_the_user_before_looking_for_a_running_timer(self):
        calls = []
        db = MagicMock()
        db.query.side_effect = lambda *_: (calls.append("query"), MagicMock())[1]  # a running timer is found
        with patch.object(timers, "check_new_timer"), \
                patch.object(timers, "lock_sessions", side_effect=lambda *_: calls.append("lock")):
            with self.assertRaises(timers.Refused):
                timers.create_timer(db, body())
        self.assertEqual(calls[:2], ["lock", "query"])


if __name__ == "__main__":
    unittest.main()

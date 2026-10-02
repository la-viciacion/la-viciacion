import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from src.database.schemas import GameTimerCreate
from src.routers import timers


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
        with self.assertRaises(HTTPException) as ctx:
            timers.check_new_timer(db_where_exist(timers.User), body())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_an_unknown_user_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            timers.check_new_timer(db_where_exist(timers.Game), body())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_an_unknown_platform_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            timers.check_new_timer(db_where_exist(timers.User, timers.Game), body(platform="nope"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_a_known_game_without_platform_passes(self):
        timers.check_new_timer(db_where_exist(timers.User, timers.Game), body())

    def test_a_known_platform_passes(self):
        timers.check_new_timer(db_where_exist(timers.User, timers.Game, timers.PlatformTag), body(platform="pc"))


if __name__ == "__main__":
    unittest.main()

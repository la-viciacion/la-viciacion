import datetime
import types
import unittest
from unittest import mock

from fastapi import HTTPException

from src.routers import timers


def db_with(timer):
    db = mock.MagicMock()
    db.query.return_value.filter.return_value.first.return_value = timer
    return db


def running(start):
    return types.SimpleNamespace(start_time=start, end_time=None, duration_seconds=None, is_active=True)


class StopTimerTests(unittest.TestCase):
    def test_a_normal_timer_gets_its_elapsed_time(self):
        start = datetime.datetime.now() - datetime.timedelta(minutes=90)
        timer = running(start)
        timers.stop_timer(db_with(timer), 1, 1)
        self.assertFalse(timer.is_active)
        self.assertAlmostEqual(timer.duration_seconds, 5400, delta=5)

    def test_a_timer_that_starts_ahead_of_the_clock_never_goes_negative(self):
        start = datetime.datetime.now() + datetime.timedelta(seconds=45)
        timer = running(start)
        timers.stop_timer(db_with(timer), 1, 1)
        self.assertEqual(timer.duration_seconds, 0)
        self.assertEqual(timer.end_time, start)


class CancelTimerTests(unittest.TestCase):
    def test_cancelling_deletes_the_timer_and_drops_its_empty_library_entry(self):
        timer = types.SimpleNamespace(
            start_time=datetime.datetime.now(), platform="pc", game_id="g1", is_active=True
        )
        db = db_with(timer)
        with mock.patch.object(timers.users_crud, "drop_empty_entry") as drop:
            timers.cancel_timer(db, 1, 7)
        db.delete.assert_called_once_with(timer)
        drop.assert_called_once()
        self.assertEqual(drop.call_args.args[1:4], (7, "g1", "pc"))
        db.commit.assert_called_once()

    def test_cancelling_a_timer_that_is_not_running_is_a_404(self):
        with self.assertRaises(HTTPException) as ctx:
            timers.cancel_timer(db_with(None), 1, 1)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

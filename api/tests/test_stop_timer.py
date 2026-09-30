import datetime
import types
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()

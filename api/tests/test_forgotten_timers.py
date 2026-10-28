import datetime
import unittest

from src.crud import time_entries
from src.database import models
from tests.sqlite_db import make_session
from tests import clock

NOW = clock.PIN


def running(db, hours_ago, user_id=1, game_id="g"):
    db.add(models.GameTimer(user_id=user_id, game_id=game_id, start_time=NOW - datetime.timedelta(hours=hours_ago), is_active=True))
    db.commit()


class ForgottenTimersTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()

    def found(self, **kw):
        return [t.game_id for t in time_entries.get_forgotten_game_timers(self.db, **kw)]

    def test_only_timers_older_than_the_threshold_count(self):
        running(self.db, 5, game_id="old")
        running(self.db, 3, game_id="recent")
        self.assertEqual(self.found(hours=4), ["old"])

    def test_finished_timers_are_ignored(self):
        self.db.add(models.GameTimer(user_id=1, game_id="done", start_time=NOW - datetime.timedelta(hours=9), is_active=False))
        self.db.commit()
        self.assertEqual(self.found(hours=4), [])

    def test_only_the_timers_that_crossed_the_line_in_the_stretch_are_returned(self):
        running(self.db, 4.5, game_id="just_crossed")
        running(self.db, 9, game_id="reminded_before")
        self.assertEqual(sorted(self.found(hours=4)), ["just_crossed", "reminded_before"])
        last_hour = (NOW - datetime.timedelta(hours=1), NOW)
        self.assertEqual(self.found(hours=4, crossed_between=last_hour), ["just_crossed"])

    def test_consecutive_stretches_hold_every_timer_exactly_once(self):
        """The reminder of the hourly job must neither repeat nor skip, whatever time the runs happen at."""
        for minutes in range(0, 5 * 60, 7):  # timers that started at all sorts of moments
            running(self.db, 4 + minutes / 60, game_id=f"t{minutes}")
        stretches = [(NOW - datetime.timedelta(hours=h + 1), NOW - datetime.timedelta(hours=h)) for h in range(-1, 6)]
        found = [game for stretch in stretches for game in self.found(hours=4, crossed_between=stretch)]
        self.assertEqual(len(found), len(set(found)))
        self.assertEqual(set(found), {t.game_id for t in time_entries.get_forgotten_game_timers(self.db, hours=4)})

    def test_the_moment_a_timer_crosses_the_line_is_its_start_plus_the_hours_not_the_time_it_is_now(self):
        running(self.db, 4.5, game_id="a")  # crossed 30 minutes ago
        crossed_then = (NOW - datetime.timedelta(minutes=40), NOW - datetime.timedelta(minutes=20))
        self.assertEqual(self.found(hours=4, crossed_between=crossed_then), ["a"])
        before = (NOW - datetime.timedelta(minutes=80), NOW - datetime.timedelta(minutes=40))
        self.assertEqual(self.found(hours=4, crossed_between=before), [])

    def test_it_can_be_limited_to_one_user(self):
        running(self.db, 5, user_id=1, game_id="mine")
        running(self.db, 5, user_id=2, game_id="theirs")
        self.assertEqual(self.found(user_id=2, hours=4), ["theirs"])


if __name__ == "__main__":
    unittest.main()

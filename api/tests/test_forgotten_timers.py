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

    def test_newly_forgotten_only_returns_timers_that_crossed_the_line_in_the_last_hour(self):
        running(self.db, 4.5, game_id="just_crossed")
        running(self.db, 9, game_id="reminded_before")
        self.assertEqual(sorted(self.found(hours=4)), ["just_crossed", "reminded_before"])
        self.assertEqual(self.found(hours=4, newly_forgotten=True), ["just_crossed"])

    def test_it_can_be_limited_to_one_user(self):
        running(self.db, 5, user_id=1, game_id="mine")
        running(self.db, 5, user_id=2, game_id="theirs")
        self.assertEqual(self.found(user_id=2, hours=4), ["theirs"])


if __name__ == "__main__":
    unittest.main()

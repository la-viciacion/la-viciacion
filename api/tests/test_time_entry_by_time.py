import datetime
import unittest

from src.crud import time_entries
from src.database import models
from tests.sqlite_db import make_session


def session(db, day, seconds, game_id="g"):
    start = datetime.datetime(2026, 3, day, 10)
    db.add(models.GameTimer(
        user_id=1, game_id=game_id, start_time=start, end_time=start + datetime.timedelta(seconds=seconds),
        duration_seconds=seconds, is_active=False,
    ))
    db.commit()


class TimeEntryByTimeTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()

    def find(self, seconds, mode):
        return time_entries.get_time_entry_by_time(self.db, 1, seconds, mode, season=2026)

    def test_empty_and_negative_sessions_never_count_as_short(self):
        session(self.db, 1, 0, "empty")
        session(self.db, 2, -30, "negative")
        session(self.db, 3, 200, "short")
        self.assertEqual(self.find(300, 2).game_id, "short")

    def test_without_any_valid_session_nothing_is_found(self):
        session(self.db, 1, 0)
        self.assertIsNone(self.find(300, 2))

    def test_the_earliest_matching_session_is_returned(self):
        session(self.db, 9, 5 * 3600, "later")
        session(self.db, 4, 6 * 3600, "earlier")
        session(self.db, 1, 3600, "too_short")
        self.assertEqual(self.find(4 * 3600, 3).game_id, "earlier")

    def test_exact_mode(self):
        session(self.db, 1, 100, "a")
        session(self.db, 2, 200, "b")
        self.assertEqual(self.find(200, 1).game_id, "b")


if __name__ == "__main__":
    unittest.main()

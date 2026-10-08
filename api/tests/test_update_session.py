import datetime
import types
import unittest

from src.database import models
from src.database.schemas import SessionUpdate
from src.routers import timers
from tests import clock
from tests.sqlite_db import make_session

ADMIN = types.SimpleNamespace(id=99, is_admin=1)
START = clock.PIN - datetime.timedelta(hours=3)
END = START + datetime.timedelta(hours=1)


class UpdateSessionTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.PlatformTag(id="pc", name="PC"), models.PlatformTag(id="ps", name="PlayStation")])
        self.timer = self.add_session("pc")
        self.db.add(models.UserGame(user_id=1, game_id="g", platform="pc", completed=0, started_date=START.date()))
        self.db.commit()

    def add_session(self, platform, start=START):
        timer = models.GameTimer(
            user_id=1, game_id="g", platform=platform, start_time=start,
            end_time=start + datetime.timedelta(hours=1), duration_seconds=3600, is_active=False,
        )
        self.db.add(timer)
        self.db.commit()
        return timer

    def entries(self):
        return sorted(e.platform for e in self.db.query(models.UserGame).all())

    def change_platform(self, platform="ps"):
        timers.update_session(self.db, ADMIN, self.timer.id, SessionUpdate(platform=platform))

    def test_moving_the_only_session_to_another_platform_moves_the_entry(self):
        self.change_platform()
        self.assertEqual(self.entries(), ["ps"])

    def test_an_entry_that_keeps_other_sessions_stays(self):
        self.add_session("pc", start=START - datetime.timedelta(hours=5))
        self.change_platform()
        self.assertEqual(self.entries(), ["pc", "ps"])

    def test_a_completed_entry_stays(self):
        self.db.query(models.UserGame).update({"completed": 1})
        self.db.commit()
        self.change_platform()
        self.assertEqual(self.entries(), ["pc", "ps"])

    def test_editing_only_the_notes_touches_no_entry(self):
        timers.update_session(self.db, ADMIN, self.timer.id, SessionUpdate(notes="ok"))
        self.assertEqual(self.entries(), ["pc"])


if __name__ == "__main__":
    unittest.main()

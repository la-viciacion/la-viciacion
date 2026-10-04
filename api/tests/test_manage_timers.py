import datetime
import unittest

from fastapi import BackgroundTasks, HTTPException

from src.database import models
from src.routers import manage
from tests.sqlite_db import make_session

START = datetime.datetime(2026, 3, 1, 10)


class ChangeSessionGameTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.Game(id="doom", name="Doom"), models.Game(id="hades", name="Hades")])
        self.timer = models.GameTimer(
            user_id=1, game_id="doom", platform="pc", start_time=START, end_time=START + datetime.timedelta(hours=1),
            duration_seconds=3600, is_active=False,
        )
        self.db.add(self.timer)
        self.db.add(models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=START.date(), completed=0))
        self.db.commit()

    def patch(self, **fields):
        return manage.patch_timer(self.timer.id, manage.TimerPatch(**fields), BackgroundTasks(), self.db)

    def entries(self):
        return sorted((e.game_id, e.platform, e.season) for e in self.db.query(models.UserGame).filter_by(user_id=1))

    def test_the_session_moves_to_the_other_game_with_its_library_entry(self):
        self.patch(game_id="hades")
        self.assertEqual(self.db.get(models.GameTimer, self.timer.id).game_id, "hades")
        # the new game gets its entry and the old one, left with nothing, goes
        self.assertEqual(self.entries(), [("hades", "pc", 2026)])

    def test_the_old_entry_stays_when_it_still_has_sessions(self):
        self.db.add(models.GameTimer(
            user_id=1, game_id="doom", platform="pc", start_time=START + datetime.timedelta(days=1),
            end_time=START + datetime.timedelta(days=1, hours=1), duration_seconds=3600, is_active=False,
        ))
        self.db.commit()
        self.patch(game_id="hades")
        self.assertEqual(self.entries(), [("doom", "pc", 2026), ("hades", "pc", 2026)])

    def test_a_completed_old_entry_is_kept(self):
        entry = self.db.query(models.UserGame).one()
        entry.completed = 1
        self.db.commit()
        self.patch(game_id="hades")
        self.assertEqual(self.entries(), [("doom", "pc", 2026), ("hades", "pc", 2026)])

    def test_an_unknown_game_is_a_404_and_nothing_changes(self):
        with self.assertRaises(HTTPException) as ctx:
            self.patch(game_id="nope")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(self.db.get(models.GameTimer, self.timer.id).game_id, "doom")

    def test_leaving_the_game_out_or_null_keeps_it(self):
        self.patch(notes="x")
        self.patch(game_id=None)
        self.assertEqual(self.db.get(models.GameTimer, self.timer.id).game_id, "doom")
        self.assertEqual(self.entries(), [("doom", "pc", 2026)])

    def test_moving_the_session_to_another_season_follows_too(self):
        self.patch(start_time=datetime.datetime(2025, 12, 31, 22), end_time=datetime.datetime(2025, 12, 31, 23))
        self.assertEqual(self.entries(), [("doom", "pc", 2025)])


if __name__ == "__main__":
    unittest.main()

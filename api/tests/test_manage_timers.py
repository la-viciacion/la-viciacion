import datetime
import unittest

from fastapi import BackgroundTasks, HTTPException

from src.crud import users as users_crud
from src.database import models
from src.routers.manage import sessions
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
        return sessions.patch_timer(self.timer.id, sessions.TimerPatch(**fields), BackgroundTasks(), self.db)

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


class BulkChangeSessionsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.Game(id="doom", name="Doom"), models.Game(id="hades", name="Hades")])
        self.db.commit()
        # three sessions of doom without platform in 2026 and one in 2025, plus one of another player
        self.ids = [self.session(1, "doom", None, START + datetime.timedelta(days=d)) for d in range(3)]
        self.old = self.session(1, "doom", None, datetime.datetime(2025, 6, 1, 10))
        self.other = self.session(2, "doom", None, START)
        self.db.commit()

    def session(self, user_id, game_id, platform, start):
        users_crud.ensure_library_entry(self.db, user_id, game_id, platform, start)  # one entry per season, as the app makes them
        self.db.flush()
        timer = models.GameTimer(
            user_id=user_id, game_id=game_id, platform=platform, start_time=start, end_time=start + datetime.timedelta(hours=1),
            duration_seconds=3600, is_active=False,
        )
        self.db.add(timer)
        self.db.flush()
        return timer.id

    def bulk(self, ids, **fields):
        return sessions.patch_timers(sessions.TimerBulkPatch(ids=ids, **fields), BackgroundTasks(), self.db)

    def platforms(self, ids):
        return [self.db.get(models.GameTimer, i).platform for i in ids]

    def entries(self, user_id=1):
        found = self.db.query(models.UserGame).filter_by(user_id=user_id)
        return sorted(((e.game_id, e.platform, e.season) for e in found), key=lambda e: (e[0], e[1] or "", e[2]))

    def test_every_session_gets_the_platform_and_the_library_follows(self):
        self.assertEqual(self.bulk(self.ids, platform="pc"), {"updated": 3})
        self.assertEqual(self.platforms(self.ids), ["pc"] * 3)
        # the sessions of another season and of another player are left alone
        self.assertEqual(self.platforms([self.old, self.other]), [None, None])
        # one entry for the 2026 sessions (the empty one without platform goes); the 2025 one stays
        self.assertEqual(self.entries(), [("doom", None, 2025), ("doom", "pc", 2026)])
        self.assertEqual(self.entries(2), [("doom", None, 2026)])

    def test_a_null_platform_clears_it(self):
        self.bulk(self.ids, platform="pc")
        self.bulk(self.ids, platform=None)
        self.assertEqual(self.platforms(self.ids), [None] * 3)
        self.assertEqual(self.entries(), [("doom", None, 2025), ("doom", None, 2026)])

    def test_the_game_changes_for_all_of_them(self):
        self.bulk(self.ids, game_id="hades")
        self.assertEqual(self.entries(), [("doom", None, 2025), ("hades", None, 2026)])

    def test_the_old_entry_stays_while_a_session_is_left_in_it(self):
        self.bulk(self.ids[:2], platform="pc")
        self.assertEqual(self.entries(), [("doom", None, 2025), ("doom", None, 2026), ("doom", "pc", 2026)])

    def test_the_duration_and_the_dates_are_untouched(self):
        self.bulk(self.ids, platform="pc")
        timer = self.db.get(models.GameTimer, self.ids[0])
        self.assertEqual((timer.start_time, timer.duration_seconds, timer.is_active), (START, 3600, False))

    def test_a_session_that_does_not_exist_is_a_404_and_nothing_changes(self):
        with self.assertRaises(HTTPException) as ctx:
            self.bulk([*self.ids, 9999], platform="pc")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(self.platforms(self.ids), [None] * 3)

    def test_an_unknown_game_is_a_404_and_nothing_changes(self):
        with self.assertRaises(HTTPException) as ctx:
            self.bulk(self.ids, game_id="nope")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_something_to_change_is_needed(self):
        with self.assertRaises(HTTPException) as ctx:
            self.bulk(self.ids)
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(HTTPException) as ctx:
            self.bulk(self.ids, game_id=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_repeated_ids_count_once_and_the_selection_has_a_size(self):
        self.assertEqual(self.bulk([self.ids[0], self.ids[0]], platform="pc"), {"updated": 1})
        with self.assertRaises(ValueError):
            sessions.TimerBulkPatch(ids=[])
        with self.assertRaises(ValueError):
            sessions.TimerBulkPatch(ids=list(range(sessions.BULK_MAX + 1)))


if __name__ == "__main__":
    unittest.main()

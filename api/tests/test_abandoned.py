import datetime
import unittest

from fastapi import HTTPException

from src.crud import users
from src.database import models, schemas
from src.routers import users as users_router
from src.utils import messages as msg
from tests.sqlite_db import make_session
from tests import clock

NOW = clock.PIN
YEAR = NOW.year


def entry(**fields):
    return models.UserGame(**{"user_id": 1, "game_id": "doom", "started_date": datetime.date(YEAR, 1, 2), "completed": 0, **fields})


class IsAbandonedTests(unittest.TestCase):
    def test_an_entry_nobody_gave_up_is_not_abandoned(self):
        self.assertFalse(users.is_abandoned(entry(), NOW))
        self.assertFalse(users.is_abandoned(entry(), None))

    def test_it_is_abandoned_from_the_mark_until_the_game_is_played_again(self):
        marked = entry(abandoned_at=NOW)
        self.assertTrue(users.is_abandoned(marked, None))  # no session at all
        self.assertTrue(users.is_abandoned(marked, NOW - datetime.timedelta(days=3)))  # last played before
        self.assertTrue(users.is_abandoned(marked, NOW))  # the very moment
        self.assertFalse(users.is_abandoned(marked, NOW + datetime.timedelta(minutes=1)))  # played again: resumed

    def test_a_completed_entry_is_never_abandoned(self):
        self.assertFalse(users.is_abandoned(entry(abandoned_at=NOW, completed=1), None))


class LibraryItemTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1, is_admin=0),
            models.Game(id="doom", name="Doom"),
            models.PlatformTag(id="pc", name="PC"),
        ])
        self.db.commit()

    def add(self, **fields):
        row = models.UserGame(**{"user_id": 1, "game_id": "doom", "platform": "pc", "started_date": datetime.date(YEAR, 1, 2), "completed": 0, **fields})
        self.db.add(row)
        self.db.commit()
        return row

    def play(self, when):
        self.db.add(models.GameTimer(user_id=1, game_id="doom", platform="pc", start_time=when, end_time=when + datetime.timedelta(hours=1), duration_seconds=3600, is_active=False))
        self.db.commit()

    def item(self, row):
        return users.get_library_item(self.db, 1, row.id)

    def test_a_pending_entry_of_the_season_can_be_given_up_but_not_resumed(self):
        got = self.item(self.add())
        self.assertEqual((got["abandoned"], got["can_abandon"], got["can_resume"]), (False, True, False))

    def test_an_abandoned_entry_can_be_resumed_and_completed_but_not_abandoned_again(self):
        got = self.item(self.add(abandoned_at=NOW))
        self.assertEqual((got["abandoned"], got["can_abandon"], got["can_resume"], got["can_complete"]), (True, False, True, True))

    def test_playing_after_the_mark_resumes_it(self):
        row = self.add(abandoned_at=NOW - datetime.timedelta(days=2))
        self.play(NOW - datetime.timedelta(days=1))
        got = self.item(row)
        self.assertEqual((got["abandoned"], got["can_abandon"], got["can_resume"]), (False, True, False))

    def test_playing_before_the_mark_leaves_it_abandoned(self):
        row = self.add(abandoned_at=NOW)
        self.play(NOW - datetime.timedelta(days=1))
        self.assertTrue(self.item(row)["abandoned"])

    def test_a_completed_entry_offers_neither(self):
        got = self.item(self.add(completed=1, completed_date=datetime.date(YEAR, 1, 5)))
        self.assertEqual((got["abandoned"], got["can_abandon"], got["can_resume"]), (False, False, False))

    def test_a_closed_season_offers_neither(self):
        row = models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(YEAR - 1, 3, 1), completed=0, abandoned_at=datetime.datetime(YEAR - 1, 4, 1))
        self.db.add(row)
        self.db.commit()
        got = self.item(row)
        self.assertEqual((got["abandoned"], got["can_abandon"], got["can_resume"]), (True, False, False))

    def test_completing_clears_the_mark(self):
        row = self.add(abandoned_at=NOW)
        users.complete_entry(self.db, row)
        self.assertIsNone(self.db.get(models.UserGame, row.id).abandoned_at)


class AbandonRouteTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.ana = models.User(id=1, name="Ana", username="ana", is_active=1, is_admin=0)
        self.bea = models.User(id=2, name="Bea", username="bea", is_active=1, is_admin=0)
        self.root = models.User(id=3, name="Root", username="root", is_active=1, is_admin=1)
        self.db.add_all([self.ana, self.bea, self.root, models.Game(id="doom", name="Doom"), models.PlatformTag(id="pc", name="PC")])
        self.row = models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(YEAR, 1, 2), completed=0)
        self.db.add(self.row)
        self.db.commit()

    def call(self, abandoned, actor=None, username="ana", entry_id=None):
        return users_router.update_abandoned(username, entry_id or self.row.id, schemas.AbandonUpdate(abandoned=abandoned), actor or self.ana, self.db)

    def refused(self, call, status):
        with self.assertRaises(HTTPException) as ctx:
            call()
        self.assertEqual(ctx.exception.status_code, status, ctx.exception.detail)
        return ctx.exception.detail

    def test_marking_and_taking_back(self):
        self.assertTrue(self.call(True)["abandoned"])
        self.assertIsNotNone(self.db.get(models.UserGame, self.row.id).abandoned_at)
        self.assertFalse(self.call(False)["abandoned"])
        self.assertIsNone(self.db.get(models.UserGame, self.row.id).abandoned_at)

    def test_marking_twice_is_harmless(self):
        self.call(True)
        self.assertTrue(self.call(True)["abandoned"])

    def test_an_admin_can_do_it_for_a_player_and_another_player_cannot(self):
        self.assertTrue(self.call(True, actor=self.root)["abandoned"])
        self.refused(lambda: self.call(True, actor=self.bea), 403)

    def test_an_entry_of_somebody_else_is_not_found(self):
        self.refused(lambda: self.call(True, actor=self.bea, username="bea", entry_id=self.row.id), 404)

    def test_a_completed_game_cannot_be_abandoned(self):
        self.row.completed = 1
        self.db.commit()
        self.assertEqual(self.refused(lambda: self.call(True), 409), msg.ABANDON_COMPLETED)

    def test_a_closed_season_is_frozen(self):
        old = models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(YEAR - 1, 3, 1), completed=0)
        self.db.add(old)
        self.db.commit()
        self.assertEqual(self.refused(lambda: self.call(True, entry_id=old.id), 409), msg.ABANDON_ONLY_CURRENT_SEASON)
        self.assertEqual(self.refused(lambda: self.call(False, entry_id=old.id), 409), msg.ABANDON_ONLY_CURRENT_SEASON)

    def test_an_unknown_entry_is_a_404(self):
        self.refused(lambda: self.call(True, entry_id=999), 404)


if __name__ == "__main__":
    unittest.main()

import datetime
import unittest

from src.crud import early_access, game_catalog, game_overview
from src.database import models
from src.utils import igdb_sync
from tests.clock import today
from tests.sqlite_db import make_session

D = datetime.date
TODAY = D(2026, 10, 4)


class TheRuleTests(unittest.TestCase):
    def test_a_game_is_in_early_access_from_its_day_until_the_launch_is_reached(self):
        self.assertFalse(early_access.is_early_access(None, None, TODAY))  # it never had one
        self.assertFalse(early_access.is_early_access(D(2026, 10, 5), None, TODAY))  # not begun yet
        self.assertTrue(early_access.is_early_access(TODAY, None, TODAY))  # begins today, no launch announced
        self.assertTrue(early_access.is_early_access(D(2024, 1, 1), None, TODAY))
        self.assertTrue(early_access.is_early_access(D(2024, 1, 1), D(2026, 10, 5), TODAY))  # the launch is tomorrow
        self.assertFalse(early_access.is_early_access(D(2024, 1, 1), TODAY, TODAY))  # the launch day: it is out
        self.assertFalse(early_access.is_early_access(D(2024, 1, 1), D(2025, 6, 1), TODAY))

    def test_it_ends_by_itself_when_the_day_goes_by(self):
        went_in, launch = D(2024, 1, 1), D(2026, 10, 5)
        self.assertTrue(early_access.is_early_access(went_in, launch, TODAY))
        self.assertFalse(early_access.is_early_access(went_in, launch, launch))


class ToRefreshTests(unittest.TestCase):
    def test_only_linked_games_in_early_access_whose_launch_is_not_reached_are_refreshed_the_soonest_first(self):
        db = make_session()
        db.add_all([
            models.Game(id="far", name="Far", igdb_id=1, early_access_date=D(2024, 1, 1), release_date=D(2027, 6, 1)),
            models.Game(id="soon", name="Soon", igdb_id=2, early_access_date=D(2024, 1, 1), release_date=D(2026, 11, 1)),
            models.Game(id="tba", name="Tba", igdb_id=3, early_access_date=D(2024, 1, 1)),
            models.Game(id="today", name="Today", igdb_id=4, early_access_date=D(2024, 1, 1), release_date=TODAY),  # the day it ends: one last look
            models.Game(id="out", name="Out", igdb_id=5, early_access_date=D(2022, 1, 1), release_date=D(2023, 1, 1)),
            models.Game(id="plain", name="Plain", igdb_id=6, release_date=D(2027, 1, 1)),
            models.Game(id="nolink", name="No link", early_access_date=D(2024, 1, 1)),
        ])
        db.commit()
        self.assertEqual([g.id for g in early_access.to_refresh(db, TODAY)], ["today", "soon", "far", "tba"])


class ApplyDaysTests(unittest.TestCase):
    def test_the_days_igdb_gives_are_written_and_a_blank_never_overwrites(self):
        game = models.Game(id="g", name="G", release_date=D(2025, 1, 1), early_access_date=D(2024, 1, 1))
        self.assertEqual(igdb_sync.apply_days(game, None, None), [])
        self.assertEqual((game.release_date, game.early_access_date), (D(2025, 1, 1), D(2024, 1, 1)))
        self.assertEqual(igdb_sync.apply_days(game, D(2026, 3, 1), D(2023, 5, 5)), ["early_access_date", "release_date"])
        self.assertEqual((game.release_date, game.early_access_date), (D(2026, 3, 1), D(2023, 5, 5)))

    def test_a_launch_that_is_the_early_access_day_goes_blank_when_igdb_has_no_launch(self):
        game = models.Game(id="g", name="G", release_date=D(2024, 1, 1))  # RAWG dates an early access game by the day it went in
        self.assertEqual(igdb_sync.apply_days(game, None, D(2024, 1, 1)), ["early_access_date", "release_date"])
        self.assertIsNone(game.release_date)
        other = models.Game(id="h", name="H", release_date=D(2025, 2, 2))  # a different day: somebody's, not RAWG's early access
        igdb_sync.apply_days(other, None, D(2024, 1, 1))
        self.assertEqual(other.release_date, D(2025, 2, 2))


class TheGameListsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        t = today()
        self.db.add_all([
            models.User(id=1, username="ana", name="Ana", is_active=1),
            models.Game(id="ea", name="Ea", early_access_date=t - datetime.timedelta(days=30)),
            models.Game(id="ended", name="Ended", early_access_date=t - datetime.timedelta(days=90), release_date=t),  # launched today
            models.Game(id="plain", name="Plain"),
        ])
        self.db.commit()

    def test_the_catalogue_flags_and_filters_the_games_in_early_access(self):
        rows = {r["id"]: r["early_access"] for r in game_catalog.catalog(self.db, 1)["items"]}
        self.assertEqual(rows, {"ea": True, "ended": False, "plain": False})
        only = game_catalog.catalog(self.db, 1, early_access=True)
        self.assertEqual(([r["id"] for r in only["items"]], only["total"]), (["ea"], 1))

    def test_the_game_page_says_when_it_went_in_and_whether_it_still_is(self):
        game = game_overview.overview(self.db, "ea", 1)["game"]
        self.assertEqual((game["early_access"], game["early_access_date"]), (True, today() - datetime.timedelta(days=30)))
        self.assertFalse(game_overview.overview(self.db, "ended", 1)["game"]["early_access"])

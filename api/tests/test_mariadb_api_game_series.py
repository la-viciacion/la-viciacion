"""The saga of a game through real requests (MariaDB required, see api_support.py); RAWG is replaced by a recorder."""
from unittest import mock

from src.database import database, models
from src.utils import igdb_series, rawg_series
from tests import clock
from tests.api_support import ApiTestCase
from tests.clock import ago

TODAY = clock.today


class GameSeriesTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.god = self.user("admin", admin=True)  # the emergency account (models.GOD_USERNAME)
        self.game("hades", "Hades", rawg_id=100, release_date=clock.today().replace(year=2020, month=9, day=17), slug="hades")
        self.game("hades-2", "Hades II", rawg_id=200)
        self.game("alone", "Alone")  # no RAWG id
        self.series = mock.AsyncMock(return_value=[
            {"rawg_id": 200, "name": "Hades II", "slug": "hades-ii", "image_url": "http://img/2", "released": "2025-05-06"},
            {"rawg_id": 300, "name": "Hades Remix", "slug": "hades-remix", "image_url": None, "released": "2022-01-01"},
        ])
        self.igdb_series = mock.AsyncMock(return_value=None)
        for patcher in (mock.patch.object(rawg_series, "series_of", self.series), mock.patch.object(igdb_series, "series_of", self.igdb_series)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def saga(self, game="hades", as_user="ana"):
        return self.api("GET", f"/games/{game}/series", as_user=as_user)

    def test_it_needs_a_login_and_an_unknown_game_is_a_404(self):
        self.assertEqual(self.api("GET", "/games/hades/series").status_code, 401)
        self.assertEqual(self.saga("nope").status_code, 404)

    def test_a_game_without_a_rawg_id_has_no_saga_and_rawg_is_not_asked(self):
        self.assertEqual(self.saga("alone").json(), {"available": False, "games": []})
        self.series.assert_not_awaited()

    def test_a_game_with_an_igdb_id_gets_igdbs_series_matched_by_igdb_id_and_rawg_is_not_asked(self):
        self.game("witcher", "The Witcher", igdb_id=900, rawg_id=901, slug="the-witcher", release_date=clock.today().replace(year=2007, month=10, day=30))
        self.game("witcher-2", "The Witcher 2", igdb_id=902)
        self.igdb_series.return_value = [
            {"igdb_id": 902, "rawg_id": None, "name": "The Witcher 2: Assassins of Kings", "slug": "the-witcher-2", "image_url": None, "released": "2011-05-17"},
            {"igdb_id": 903, "rawg_id": None, "name": "The Witcher 3", "slug": "the-witcher-3-wild-hunt", "image_url": "http://img/3", "released": "2015-05-19"},
        ]
        games = self.saga("witcher").json()["games"]
        self.assertEqual([(g["name"], g["game_id"], g["current"]) for g in games], [("The Witcher", "witcher", True), ("The Witcher 2", "witcher-2", False), ("The Witcher 3", None, False)])
        self.assertEqual(games[1]["players"], 0)
        self.assertEqual(games[2]["url"], "https://www.igdb.com/games/the-witcher-3-wild-hunt")  # not ours: IGDB's page
        self.assertEqual(games[0]["url"], "https://rawg.io/games/the-witcher")  # ours has a RAWG id: its slug is RAWG's
        self.igdb_series.assert_awaited_once_with(900)
        self.series.assert_not_awaited()

    def test_when_igdb_cannot_say_the_series_of_a_game_with_a_rawg_id_comes_from_rawg(self):
        self.game("both", "Both", igdb_id=1, rawg_id=300)
        self.assertTrue(self.saga("both").json()["available"])
        self.igdb_series.assert_awaited_once_with(1)
        self.series.assert_awaited_once_with(300)

    def test_a_game_with_only_an_igdb_id_has_no_saga_when_igdb_cannot_say(self):
        self.game("igdb-only", "Igdb Only", igdb_id=2)
        self.assertEqual(self.saga("igdb-only").json(), {"available": False, "games": []})
        self.series.assert_not_awaited()

    def test_when_rawg_cannot_be_asked_the_page_has_no_saga(self):
        self.series.return_value = None
        self.assertEqual(self.saga().json(), {"available": False, "games": []})

    def test_a_game_with_no_series_is_available_but_empty(self):
        self.series.return_value = []
        self.assertEqual(self.saga().json(), {"available": True, "games": []})

    def test_the_games_come_in_order_of_release_with_the_catalogue_matched_by_rawg_id(self):
        body = self.saga().json()
        self.assertTrue(body["available"])
        self.assertEqual([(g["name"], g["current"], g["game_id"]) for g in body["games"]], [("Hades", True, "hades"), ("Hades Remix", False, None), ("Hades II", False, "hades-2")])
        remix = body["games"][1]
        self.assertEqual((remix["slug"], remix["mine"], remix["players"]), ("hades-remix", None, 0))  # not in the catalogue: nothing of it is anybody's
        self.series.assert_awaited_once_with(100)

    def test_each_game_of_the_catalogue_says_what_the_viewer_has_and_how_many_players_have_it(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.session(self.ana, "hades", ago(hours=5), 90)
        self.library_entry(self.ana, "hades-2", TODAY(), "pc")
        self.library_entry(self.bea, "hades-2", TODAY(), "pc")
        self.library_entry(self.god, "hades-2", TODAY(), "pc")  # the emergency account is not a player
        games = {g["game_id"]: g for g in self.saga().json()["games"] if g["game_id"]}
        self.assertEqual(games["hades"]["mine"], {"has": True, "completed": True, "seconds": 5400})
        self.assertEqual(games["hades-2"]["mine"], {"has": True, "completed": False, "seconds": 0})
        self.assertEqual((games["hades"]["players"], games["hades-2"]["players"]), (1, 2))
        other = {g["game_id"]: g for g in self.saga(as_user="bea").json()["games"] if g["game_id"]}
        self.assertIsNone(other["hades"]["mine"])  # bea does not have the first one

    def test_the_next_is_the_first_after_this_game_that_you_have_not_completed(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc", completed=1, completed_date=TODAY())
        games = self.saga().json()["games"]
        self.assertEqual([g["name"] for g in games if g["next"]], ["Hades Remix"])
        self.library_entry(self.ana, "hades-2", TODAY(), "pc")
        self.assertEqual([g["name"] for g in self.saga("hades-2").json()["games"] if g["next"]], [])  # the last one of the saga

    def test_the_title_and_the_cover_of_the_catalogue_win_over_rawgs(self):
        with database.SessionLocal() as db:
            db.query(models.Game).filter_by(id="hades-2").update({"name": "Hades II (nuestro)", "image_url": "http://ours"})
            db.commit()
        games = {g["rawg_id"]: g for g in self.saga().json()["games"]}
        self.assertEqual((games[200]["name"], games[200]["image_url"]), ("Hades II (nuestro)", "http://ours"))
        self.assertEqual(games[300]["image_url"], None)

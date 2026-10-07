"""The games catalog (the Juegos page) through real requests (MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta

from src.database import database, models
from tests.api_support import ApiTestCase

TODAY = datetime.date.today


class GameCatalogTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.gone = self.user("gone", active=False)
        self.game("celeste", "Celeste", genres="Platformer, Indie", release_date=datetime.date(2018, 1, 25))
        self.game("hades", "Hades", genres="Roguelike, Indie", release_date=datetime.date(2020, 9, 17))
        self.game("zelda", "Zelda", genres="Adventure", release_date=datetime.date(2017, 3, 3))
        self.game("nobody", "Nobody Has It")

    def catalog(self, as_user="ana", **params):
        return self.api("GET", "/games/catalog", as_user=as_user, params=params).json()

    def names(self, **params):
        return [g["name"] for g in self.catalog(**params)["items"]]

    def rate(self, user_id, game_id, score):
        with database.SessionLocal() as db:
            db.add(models.GameScore(user_id=user_id, game_id=game_id, score=score))
            db.commit()

    def test_it_needs_a_login_and_lists_every_game_with_its_genres(self):
        self.assertEqual(self.api("GET", "/games/catalog").status_code, 401)
        body = self.catalog()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["genres"], ["Adventure", "Indie", "Platformer", "Roguelike"])

    def test_the_default_order_is_the_latest_activity_first_and_the_games_without_any_last(self):
        self.library_entry(self.ana, "celeste", TODAY() - timedelta(days=40), "pc")
        self.library_entry(self.bea, "hades", TODAY() - timedelta(days=3), "pc")
        self.library_entry(self.bea, "zelda", TODAY() - timedelta(days=10), "pc")
        self.assertEqual(self.names(), ["Hades", "Zelda", "Celeste", "Nobody Has It"])

    def test_the_players_who_are_no_longer_active_count_like_the_rest(self):
        self.library_entry(self.gone, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.session(self.gone, "celeste", datetime.datetime.now() - timedelta(hours=3), 60)
        self.rate(self.gone, "celeste", 50)
        game = next(g for g in self.catalog()["items"] if g["id"] == "celeste")
        self.assertEqual((game["players"], game["played_seconds"], game["completed_by"], game["score_count"], game["score_mean"]),
                         (1, 3600, 1, 1, 50.0))

    def test_a_game_carries_what_the_group_has_done_with_it(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.library_entry(self.bea, "celeste", TODAY(), "pc")
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=3), 60)
        self.rate(self.ana, "celeste", 90)
        self.rate(self.bea, "celeste", 70)
        game = next(g for g in self.catalog()["items"] if g["id"] == "celeste")
        self.assertEqual((game["players"], game["played_seconds"], game["completed_by"], game["score_count"], game["score_mean"]),
                         (2, 3600, 1, 2, 80.0))
        self.assertEqual((game["have"], game["my_score"], game["my_completed"]), (True, 90, True))
        self.assertIsNotNone(game["last_played"])
        self.assertIsNone(next(g for g in self.catalog()["items"] if g["id"] == "hades")["last_played"])
        other = next(g for g in self.catalog(as_user="bea")["items"] if g["id"] == "celeste")
        self.assertEqual((other["have"], other["my_score"], other["my_completed"]), (True, 70, False))

    def test_search_genre_and_library_filters(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.assertEqual(self.names(q="ELE", sort="name"), ["Celeste"])
        self.assertEqual(self.names(genre="indie", sort="name"), ["Celeste", "Hades"])
        self.assertEqual(self.names(library="have"), ["Celeste"])
        self.assertEqual(sorted(self.names(library="not")), ["Hades", "Nobody Has It", "Zelda"])
        self.assertEqual(self.api("GET", "/games/catalog", as_user="ana", params={"library": "maybe"}).status_code, 422)

    def test_completed_rated_with_players_and_playing_filters(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.library_entry(self.bea, "hades", TODAY(), "pc")
        self.rate(self.ana, "hades", 80)
        self.assertEqual(self.names(completed="true"), ["Celeste"])
        self.assertEqual(self.names(rated="true"), ["Hades"])
        self.assertEqual(sorted(self.names(with_players="true")), ["Celeste", "Hades"])
        self.api("POST", "/timers/start", as_user="bea", json={"user_id": self.bea, "game_id": "hades", "platform": "pc"})
        self.assertEqual(self.names(playing="true"), ["Hades"])
        self.assertTrue(next(g for g in self.catalog()["items"] if g["id"] == "hades")["playing_now"])

    def test_orders(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "pc")
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.session(self.ana, "hades", datetime.datetime.now() - timedelta(hours=5), 300)
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=9), 30)
        self.rate(self.ana, "celeste", 95)
        self.rate(self.ana, "hades", 60)
        self.assertEqual(self.names(sort="played")[:2], ["Hades", "Celeste"])
        self.assertEqual(self.names(sort="players")[:2], ["Celeste", "Hades"])
        self.assertEqual(self.names(sort="rated")[:2], ["Celeste", "Hades"])
        self.assertEqual(self.names(sort="release"), ["Hades", "Celeste", "Zelda", "Nobody Has It"])
        self.assertEqual(self.names(sort="name"), ["Celeste", "Hades", "Nobody Has It", "Zelda"])
        self.assertEqual(self.api("GET", "/games/catalog", as_user="ana", params={"sort": "x"}).status_code, 422)

    def test_paging(self):
        first = self.catalog(sort="name", limit=3)
        self.assertEqual((first["total"], len(first["items"])), (4, 3))
        self.assertEqual([g["name"] for g in self.catalog(sort="name", limit=3, offset=3)["items"]], ["Zelda"])
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            self.assertEqual(self.api("GET", "/games/catalog", as_user="ana", params=params).status_code, 422, params)

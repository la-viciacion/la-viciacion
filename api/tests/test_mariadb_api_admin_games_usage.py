"""The usage of each game in the admin panel, to tell an orphan from a wished-for release (MariaDB required, see api_support.py)."""
from datetime import timedelta

from src.database import database, models
from tests.api_support import ApiTestCase
from tests import clock

TODAY = clock.today


class AdminGamesUsageTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user("root", admin=True)
        self.ana = self.user("ana")
        self.game("played", "Played")
        self.game("owned", "Owned")
        self.game("soon", "Soon", release_date=TODAY() + timedelta(days=30))
        self.game("wished-out", "Wished Out")
        self.game("orphan", "Orphan")
        self.game("base", "Base")
        self.game("dlc", "Dlc", is_dlc=True, parent_game_id="base")
        self.session(self.ana, "played", clock.now() - timedelta(hours=3), 30)
        self.library_entry(self.ana, "owned", TODAY(), "pc")
        self.api("PUT", "/users/ana/wishlist/soon", as_user="ana")
        self.api("PUT", "/users/ana/wishlist/wished-out", as_user="ana")

    def games(self, **params):
        body = self.api("GET", "/manage/games", as_user="root", params=params).json()
        return {g["id"]: g for g in body["items"]}

    def test_a_game_carries_its_sessions_players_wishes_and_whether_it_is_unreleased(self):
        found = self.games()
        self.assertEqual((found["played"]["sessions"], found["played"]["unused"]), (1, False))
        self.assertEqual((found["owned"]["sessions"], found["owned"]["players"], found["owned"]["wishes"]), (0, 1, 0))
        self.assertEqual((found["soon"]["wishes"], found["soon"]["upcoming"]), (1, True))

    def test_unused_is_a_game_nothing_refers_to_and_a_wished_release_is_not(self):
        self.assertEqual(set(self.games(usage="unused")), {"orphan", "dlc"})  # the base has a DLC; the DLC itself refers to nothing

    def test_wished_games_have_no_sessions_or_players_but_somebody_waits_for_them(self):
        self.assertEqual(set(self.games(usage="wished")), {"soon", "wished-out"})

    def test_unplayed_is_every_game_without_sessions_or_players(self):
        self.assertEqual(set(self.games(usage="unplayed")), {"soon", "wished-out", "orphan", "base", "dlc"})

    def test_it_sorts_by_wishes(self):
        self.api("PUT", "/users/ana/wishlist/orphan", as_user="ana")
        self.api("PUT", "/users/root/wishlist/orphan", as_user="root")
        body = self.api("GET", "/manage/games", as_user="root", params={"sort": "wishes", "order": "desc"}).json()
        self.assertEqual(body["items"][0]["id"], "orphan")

    def test_the_filter_refuses_an_unknown_value(self):
        self.assertEqual(self.api("GET", "/manage/games", as_user="root", params={"usage": "x"}).status_code, 422)

    def test_the_people_of_a_game_are_who_has_it_and_who_wishes_for_it_whatever_their_state(self):
        gone = self.user("gone", active=False)
        self.library_entry(gone, "owned", TODAY(), None)
        with database.SessionLocal() as db:  # an inactive account cannot sign in: its wish is written straight to the table
            db.add(models.UserWishlist(user_id=gone, game_id="soon"))
            db.commit()
        owned = self.api("GET", "/manage/games/owned/people", as_user="root").json()
        self.assertEqual([(p["username"], p["is_active"], [e["platform"] for e in p["entries"]]) for p in owned["players"]], [("ana", True, ["pc"]), ("gone", False, [None])])
        self.assertEqual(owned["wishes"], [])
        soon = self.api("GET", "/manage/games/soon/people", as_user="root").json()
        self.assertEqual([(p["username"], p["is_active"]) for p in soon["wishes"]], [("ana", True), ("gone", False)])
        self.assertEqual(self.api("GET", "/manage/games/nope/people", as_user="root").status_code, 404)
        self.assertEqual(self.api("GET", "/manage/games/soon/people", as_user="ana").status_code, 403)

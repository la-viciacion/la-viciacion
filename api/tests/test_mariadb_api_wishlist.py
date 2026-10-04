"""The wishlist through real requests (MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta

from src.database import database, models
from tests.api_support import ApiTestCase

TODAY = datetime.date.today


class WishlistTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.game("soon", "Soon", release_date=TODAY() + timedelta(days=30))
        self.game("tba", "Tba")
        self.game("out", "Out", release_date=datetime.date(2020, 1, 1))

    def wish(self, game, as_user="ana", username=None):
        return self.api("PUT", f"/users/{username or as_user}/wishlist/{game}", as_user=as_user)

    def unwish(self, game, as_user="ana", username=None):
        return self.api("DELETE", f"/users/{username or as_user}/wishlist/{game}", as_user=as_user)

    def wishlist(self, as_user="ana"):
        return self.api("GET", "/group/wishlist", as_user=as_user).json()

    def test_it_needs_a_login(self):
        self.assertEqual(self.api("GET", "/group/wishlist").status_code, 401)
        self.assertEqual(self.api("PUT", "/users/ana/wishlist/soon").status_code, 401)

    def test_a_player_wishes_and_unwishes_a_game(self):
        self.assertEqual(self.wish("soon").json(), {"game_id": "soon", "wished": True})
        self.assertEqual([g["id"] for g in self.wishlist()["upcoming"]], ["soon"])
        self.assertEqual(self.unwish("soon").json(), {"game_id": "soon", "wished": False})
        self.assertEqual(self.wishlist(), {"upcoming": [], "wanted": []})

    def test_wishing_twice_or_unwishing_what_is_not_there_is_harmless(self):
        self.assertEqual(self.wish("soon").status_code, 200)
        self.assertEqual(self.wish("soon").status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_wishlist"), 1)
        self.assertEqual(self.unwish("out").status_code, 200)

    def test_an_unknown_game_is_a_404_and_a_game_of_the_library_a_409(self):
        self.assertEqual(self.wish("nope").status_code, 404)
        self.library_entry(self.ana, "out", TODAY(), "pc")
        self.assertEqual(self.wish("out").status_code, 409)

    def test_nobody_edits_somebody_elses_list_but_an_admin_can(self):
        self.assertEqual(self.wish("soon", as_user="bea", username="ana").status_code, 403)
        self.assertEqual(self.unwish("soon", as_user="bea", username="ana").status_code, 403)
        self.user("root", admin=True)
        self.assertEqual(self.wish("soon", as_user="root", username="ana").status_code, 200)
        self.assertEqual([g["id"] for g in self.wishlist()["upcoming"]], ["soon"])

    def test_the_list_orders_the_upcoming_by_date_and_splits_off_the_released(self):
        for game in ("tba", "out", "soon"):
            self.wish(game)
        body = self.wishlist()
        self.assertEqual([g["id"] for g in body["upcoming"]], ["soon", "tba"])
        self.assertEqual(body["upcoming"][0]["days_until"], 30)
        self.assertIsNone(body["upcoming"][1]["days_until"])
        self.assertEqual([g["id"] for g in body["wanted"]], ["out"])

    def test_playing_a_wished_game_takes_it_off_the_list(self):
        self.wish("out")
        self.library_entry(self.ana, "out", TODAY(), "pc")
        self.assertEqual(self.wishlist(), {"upcoming": [], "wanted": []})

    def test_the_list_and_the_game_page_say_who_else_wants_it(self):
        self.wish("soon")
        self.wish("soon", as_user="bea")
        self.assertEqual([w["name"] for w in self.wishlist()["upcoming"][0]["wanted_by"]], ["Bea"])
        page = self.api("GET", "/games/soon/overview", as_user="ana").json()
        self.assertEqual((page["wished"], [w["name"] for w in page["wanted_by"]]), (True, ["Bea"]))
        self.assertEqual(self.api("GET", "/games/tba/overview", as_user="ana").json()["wished"], False)

    def test_the_catalog_marks_the_games_you_wish(self):
        self.wish("soon")
        items = {g["id"]: g["wished"] for g in self.api("GET", "/games/catalog", as_user="ana").json()["items"]}
        self.assertEqual(items, {"soon": True, "tba": False, "out": False})
        other = {g["id"]: g["wished"] for g in self.api("GET", "/games/catalog", as_user="bea").json()["items"]}
        self.assertFalse(any(other.values()))

    def test_deleting_a_user_or_a_game_in_the_panel_takes_its_wishes_along(self):
        self.user("root", admin=True)
        self.wish("soon")
        self.wish("tba", as_user="bea")
        refused = self.api("DELETE", "/manage/games/soon", as_user="root")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(self.api("DELETE", "/manage/games/soon", params={"force": True}, as_user="root").status_code, 200)
        self.assertEqual(self.api("DELETE", f"/manage/users/{self.bea}", params={"force": True}, as_user="root").status_code, 200)
        with database.SessionLocal() as db:
            self.assertEqual(db.query(models.UserWishlist).count(), 0)

"""The prices of the games through real requests (MariaDB required, see api_support.py): who can note and read them, what is
derived and, above all, what the group can and cannot see."""
import json
from unittest import mock

from src.crud import game_prices
from src.database import database, models
from tests import clock
from tests.api_support import ApiTestCase
from tests.clock import ago

TODAY = clock.today


class PriceTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.cai = self.user("cai")
        self.dan = self.user("dan")
        self.root = self.user("root", admin=True)
        self.game("hades", "Hades")
        self.game("celeste", "Celeste")

    def price(self, username="ana", game="hades", platform="pc", amount=None, as_user=None):
        return self.api("PUT", f"/users/{username}/games/{game}/price", as_user=as_user or username, json={"platform": platform, "amount": amount})

    def own(self, user, game, platform="pc", hours=1.0, cents=None):
        """The game in the library of `user` with a session of `hours` and, if given, a price."""
        self.library_entry(user, game, TODAY(), platform)
        if hours:
            self.session(user, game, ago(hours=5), int(hours * 60))
        if cents is not None:
            with database.SessionLocal() as db:
                db.add(models.UserGamePrice(user_id=user, game_id=game, platform=platform, amount_cents=cents))
                db.commit()

    def stored(self):
        return self.rows("SELECT user_id, game_id, platform, amount_cents FROM users_game_prices ORDER BY id")


class NotingTests(PriceTestCase):
    def test_a_player_notes_the_price_of_a_game_on_a_platform_and_changes_it(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.assertEqual(self.price(amount=24.99).json(), {"game_id": "hades", "platform": "pc", "amount_cents": 2499})
        self.assertEqual(self.price(amount="29,5").json()["amount_cents"], 2950)  # a comma works, and a second call changes it
        self.assertEqual([tuple(r) for r in self.stored()], [(self.ana, "hades", "pc", 2950)])

    def test_the_same_price_saved_at_the_same_moment_is_updated_not_an_error(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        real = game_prices.cents_of

        def rival(amount):  # another request saves its price after this one found none and before it writes
            with database.SessionLocal() as db:
                db.add(models.UserGamePrice(user_id=self.ana, game_id="hades", platform="pc", amount_cents=1000))
                db.commit()
            return real(amount)
        with mock.patch.object(game_prices, "cents_of", rival):
            self.assertEqual(self.price(amount=24.99).status_code, 200)
        self.assertEqual([tuple(r) for r in self.stored()], [(self.ana, "hades", "pc", 2499)])

    def test_each_platform_has_its_own_price_and_a_free_game_is_zero(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.library_entry(self.ana, "hades", TODAY(), "switch")
        self.price(platform="pc", amount=0)
        self.price(platform="switch", amount=40)
        self.assertEqual([tuple(r)[2:] for r in self.stored()], [("pc", 0), ("switch", 4000)])

    def test_a_null_amount_takes_the_price_off_and_asking_twice_is_fine(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.price(amount=10)
        self.assertIsNone(self.price(amount=None).json()["amount_cents"])
        self.assertEqual(self.price(amount=None).status_code, 200)
        self.assertEqual(self.stored(), [])

    def test_only_a_game_you_have_on_that_platform_has_a_price(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        for game, platform in (("hades", "switch"), ("celeste", "pc")):
            response = self.price(game=game, platform=platform, amount=10)
            self.assertEqual((response.status_code, response.json()["detail"]), (400, "No tienes este juego en esa plataforma"), (game, platform))
        self.assertEqual(self.stored(), [])

    def test_the_amount_is_checked(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        for bad, fragment in (("mucho", "número"), (-5, "entre 0"), (10001, "entre 0")):
            response = self.price(amount=bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn(fragment, response.json()["detail"])
        self.assertEqual(self.stored(), [])

    def test_the_prices_are_yours_and_an_administrators_and_nobody_elses(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.assertEqual(self.price(username="ana", amount=10, as_user="bea").status_code, 403)
        self.assertEqual(self.price(username="ana", amount=10, as_user="root").status_code, 200)  # an admin, like the rest of the data
        self.assertEqual(self.api("GET", "/users/ana/value", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", "/users/ana/value", as_user="root").status_code, 200)
        self.assertEqual(self.api("PUT", "/users/ana/games/hades/price", json={"platform": "pc", "amount": 1}).status_code, 401)
        self.assertEqual(self.api("GET", "/users/ana/value").status_code, 401)

    def test_deleting_the_game_or_the_player_deletes_their_prices(self):
        self.own(self.ana, "hades", cents=1000)
        self.own(self.bea, "celeste", cents=500)
        self.assertEqual(self.api("DELETE", "/manage/games/hades", as_user="root", params={"force": True}).status_code, 200)
        self.assertEqual([tuple(r)[:2] for r in self.stored()], [(self.bea, "celeste")])
        self.assertEqual(self.api("DELETE", f"/manage/users/{self.bea}", as_user="root", params={"force": True}).status_code, 200)
        self.assertEqual(self.stored(), [])

    def test_the_price_goes_with_the_last_library_entry_of_the_game_on_that_platform(self):
        self.own(self.ana, "hades", hours=0, cents=1000)
        self.own(self.ana, "celeste", hours=0, cents=500)
        entry = self.scalar("SELECT id FROM users_games WHERE user_id = :u AND game_id = 'hades'", u=self.ana)
        self.assertEqual(self.api("DELETE", f"/manage/library/{entry}", as_user="root").status_code, 200)
        self.assertEqual([tuple(r)[:2] for r in self.stored()], [(self.ana, "celeste")])

    def test_an_entry_with_a_price_survives_losing_its_only_session(self):
        self.own(self.ana, "hades", hours=1.0, cents=1000)
        timer = self.scalar("SELECT id FROM game_timers WHERE user_id = :u", u=self.ana)
        self.assertEqual(self.api("DELETE", f"/timers/{timer}", as_user="ana").status_code, 200)
        self.assertEqual(len(self.stored()), 1)  # the price keeps the entry it lives in

    def test_a_price_stays_while_another_season_still_has_the_game_on_that_platform(self):
        self.own(self.ana, "hades", hours=1.0, cents=1000)
        self.library_entry(self.ana, "hades", TODAY().replace(year=TODAY().year - 1), "pc")
        timer = self.scalar("SELECT id FROM game_timers WHERE user_id = :u", u=self.ana)
        self.assertEqual(self.api("DELETE", f"/timers/{timer}", as_user="ana").status_code, 200)
        self.assertEqual(len(self.stored()), 1)

    def test_a_platform_with_prices_cannot_be_deleted(self):
        self.own(self.ana, "hades", platform="pc", cents=1000)
        with database.SessionLocal() as db:
            db.query(models.UserGame).delete()  # nothing else uses it, only the price
            db.query(models.GameTimer).delete()
            db.commit()
        response = self.api("DELETE", "/manage/platforms/pc", as_user="root")
        self.assertEqual(response.status_code, 409)
        self.assertIn("precios", response.json()["detail"])


class LibraryAndValueTests(PriceTestCase):
    def test_the_library_gives_the_price_of_each_platform_on_every_row_of_the_game(self):
        self.own(self.ana, "hades", platform="pc", cents=2499)
        self.library_entry(self.ana, "hades", TODAY(), "switch")
        item = self.api("GET", "/users/ana/library", as_user="ana").json()["items"][0]
        self.assertEqual({p["id"]: p["price_cents"] for p in item["platforms"]}, {"pc": 2499, "switch": None})
        self.assertEqual(self.api("GET", "/users/bea/library", as_user="ana").status_code, 403)  # a library is private, prices included

    def test_the_value_sums_the_purchases_and_works_out_the_cost_per_hour(self):
        self.own(self.ana, "hades", platform="pc", hours=2, cents=1000)
        self.library_entry(self.ana, "hades", TODAY(), "switch")
        with database.SessionLocal() as db:
            db.add(models.UserGamePrice(user_id=self.ana, game_id="hades", platform="switch", amount_cents=2000))
            db.commit()
        self.own(self.ana, "celeste", hours=0.1, cents=500)  # played too little: counted as spent, with no cost per hour
        body = self.api("GET", "/users/ana/value", as_user="ana").json()
        self.assertEqual((body["spent_cents"], body["priced_games"], body["counted_games"], body["counted_seconds"]), (3500, 2, 1, 7200))
        self.assertEqual(body["per_hour_cents"], 1500)  # 30 euros over 2 hours
        self.assertEqual([(g["game_id"], g["price_cents"], g["seconds"], g["per_hour_cents"]) for g in body["games"]], [("hades", 3000, 7200, 1500), ("celeste", 500, 360, None)])

    def test_with_no_prices_the_value_is_empty(self):
        body = self.api("GET", "/users/ana/value", as_user="ana").json()
        self.assertEqual((body["spent_cents"], body["priced_games"], body["per_hour_cents"], body["games"]), (0, 0, None, []))


class GroupTests(PriceTestCase):
    def group(self, as_user="ana"):
        return self.api("GET", "/group/value", as_user=as_user)

    def priced(self, game, users, cents, hours=2.0):
        for user in users:
            self.own(user, game, hours=hours, cents=cents)

    def test_a_game_with_three_players_with_prices_is_shown_with_its_mean_per_hour(self):
        self.priced("hades", (self.ana, self.bea, self.cai), 2000)  # 20 euros over 2 hours each: 10 euros an hour
        body = self.group().json()
        self.assertEqual((body["min_contributors"], body["games"]), (3, 1))
        self.assertEqual([(g["game_id"], g["game_name"], g["contributors"], g["per_hour_cents"]) for g in body["cheapest"]], [("hades", "Hades", 3, 1000)])

    def test_two_players_are_not_enough_and_the_game_is_not_there(self):
        self.priced("hades", (self.ana, self.bea), 2000)
        self.assertEqual(self.group().json()["games"], 0)
        self.assertIsNone(self.api("GET", "/games/hades/overview", as_user="ana").json()["cost_per_hour"])

    def test_a_player_who_barely_played_or_has_no_price_does_not_count(self):
        self.priced("hades", (self.ana, self.bea), 2000)
        self.own(self.cai, "hades", hours=0.1, cents=2000)  # too little time
        self.own(self.dan, "hades", hours=2)  # no price
        self.assertEqual(self.group().json()["games"], 0)

    def test_nothing_of_a_player_is_in_the_answer_not_even_by_deduction(self):
        self.priced("hades", (self.ana, self.bea, self.cai), 2000)
        raw = self.group().text
        for secret in ("ana", "bea", "cai", "2000", "price", "amount", "user"):
            self.assertNotIn(secret, raw.replace("laviciacion", ""), secret)
        game = self.api("GET", "/games/hades/overview", as_user="dan").json()
        self.assertEqual(game["cost_per_hour"], {"per_hour_cents": 1000, "contributors": 3})
        self.assertNotIn("price", json.dumps(game["players"]))  # the players of a game never carry one
        for row in game["players"]:
            self.assertNotIn("amount_cents", row)

    def test_the_cheapest_and_the_dearest_per_hour_and_any_logged_in_player_can_ask(self):
        self.priced("hades", (self.ana, self.bea, self.cai), 400)
        self.priced("celeste", (self.ana, self.bea, self.cai), 6000)
        body = self.group(as_user="dan").json()
        self.assertEqual([g["game_id"] for g in body["cheapest"]], ["hades", "celeste"])
        self.assertEqual([g["game_id"] for g in body["priciest"]], ["celeste", "hades"])
        self.assertEqual(self.api("GET", "/group/value").status_code, 401)

    def test_the_emergency_account_is_not_a_contributor(self):
        god = self.user("admin", admin=True)  # models.GOD_USERNAME
        self.priced("hades", (self.ana, self.bea), 2000)
        self.own(god, "hades", hours=2, cents=2000)
        self.assertEqual(self.group().json()["games"], 0)

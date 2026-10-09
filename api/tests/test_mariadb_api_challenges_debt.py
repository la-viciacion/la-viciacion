"""The "reduce the debt" challenge, a personal one (MariaDB required, see api_support.py): the debt it starts from, its
two modes (a percentage of it, or games closed), what counts and what does not, and the preview the form uses."""
import datetime
from datetime import timedelta

from sqlalchemy import text

from src.database import database
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY
HOUR = 3600


class DebtTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        # Ana has three games open: 10 h of 20, 5 h of 10 and 12 h of 10 (past its average: open but owing nothing)
        for game, name, average in (("alpha", "Alpha", 20), ("beta", "Beta", 10), ("gamma", "Gamma", 10), ("fresh", "Fresh", 10)):
            self.game(game, name, avg_time=average * HOUR)
        self.old(self.ana, "alpha", 10)
        self.old(self.ana, "beta", 5)
        self.old(self.ana, "gamma", 12)

    def old(self, user, game, hours, days_ago=30):
        """A session from before today (before the challenge starts), with its library entry."""
        start = datetime.datetime.combine(TODAY(), datetime.time.min) - timedelta(days=days_ago, hours=-10)
        self.library_entry(user, game, start.date(), "pc")
        self.session(user, game, start, int(hours * 60))

    def launch_debt(self, as_user="ana", **changes):
        options = {"mode": "percent", "percent": 25, "duration": "month", **changes}
        return self.api("POST", "/challenges", as_user=as_user, json={"kind": "debt_reduction", "options": options})

    def part(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()["progress"]["players"][0]

    def complete(self, user, game):
        with database.SessionLocal() as db:
            db.execute(text("UPDATE users_games SET completed = 1, completed_date = :d WHERE user_id = :u AND game_id = :g"), {"d": TODAY(), "u": user, "g": game})
            db.commit()


class PreviewTests(DebtTestCase):
    def test_the_preview_is_the_debt_the_challenge_would_start_from(self):
        body = self.api("GET", "/challenges/debt", as_user="ana").json()
        self.assertEqual(body, {"seconds": (10 + 5) * HOUR, "games": 2, "open_games": 3})

    def test_somebody_with_nothing_open_has_nothing(self):
        self.assertEqual(self.api("GET", "/challenges/debt", as_user="bea").json(), {"seconds": 0, "games": 0, "open_games": 0})

    def test_it_needs_a_login(self):
        self.assertEqual(self.api("GET", "/challenges/debt").status_code, 401)

    def test_a_completed_or_abandoned_game_is_not_open(self):
        with database.SessionLocal() as db:
            db.execute(text("UPDATE users_games SET completed = 1, completed_date = :d WHERE game_id = 'alpha'"), {"d": TODAY() - timedelta(days=5)})
            db.execute(text("UPDATE users_games SET abandoned_at = :a WHERE game_id = 'beta'"), {"a": datetime.datetime.combine(TODAY() - timedelta(days=2), datetime.time.min)})
            db.commit()
        self.assertEqual(self.api("GET", "/challenges/debt", as_user="ana").json(), {"seconds": 0, "games": 0, "open_games": 1})  # only Gamma, which owes nothing


class LaunchTests(DebtTestCase):
    def test_a_percentage_of_the_debt_for_a_period_that_starts_today(self):
        response = self.launch_debt(percent=12.5)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["status"]), ("debt_reduction", "user", "Bajar la deuda un 12,5 %", "active"))
        self.assertEqual(body["params"], {"mode": "percent", "duration": "month", "percent": 12.5})
        self.assertEqual((body["starts_on"], body["ends_on"]), (TODAY().isoformat(), (TODAY() + timedelta(days=29)).isoformat()))

    def test_games_to_close_up_to_the_ones_that_are_open(self):
        body = self.launch_debt(mode="games", games=3, duration="week").json()
        self.assertEqual((body["title"], body["params"]), ("Cerrar 3 juegos de la deuda", {"mode": "games", "duration": "week", "games": 3}))
        self.assertEqual(self.launch_debt(mode="games", games=1).json()["title"], "Cerrar 1 juego de la deuda")

    def test_the_options_are_checked(self):
        for changes, fragment in (
            ({"mode": "hours"}, "porcentaje"), ({"duration": "year"}, "duración"), ({"percent": 0}, "porcentaje"), ({"percent": 101}, "porcentaje"),
            ({"percent": "abc"}, "número"), ({"mode": "games", "games": 0}, "entre 1 y 3"), ({"mode": "games", "games": 4}, "entre 1 y 3"),
            ({"mode": "games", "games": "x"}, "número"),
        ):
            response = self.launch_debt(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_without_open_games_there_is_nothing_to_pay(self):
        response = self.launch_debt(as_user="bea")
        self.assertEqual((response.status_code, "no hay deuda" in response.json()["detail"]), (400, True))

    def test_when_every_open_game_is_past_its_average_a_percentage_has_nothing_to_pay_but_games_can_still_be_closed(self):
        with database.SessionLocal() as db:
            db.execute(text("DELETE FROM game_timers WHERE game_id IN ('alpha', 'beta')"))
            db.commit()
        self.assertEqual(self.launch_debt().status_code, 400)
        self.assertEqual(self.launch_debt(mode="games", games=1).status_code, 201)

    def test_an_equal_one_is_refused(self):
        self.assertEqual(self.launch_debt().status_code, 201)
        self.assertEqual(self.launch_debt().status_code, 409)
        self.assertEqual(self.launch_debt(percent=30).status_code, 201)


class PercentTests(DebtTestCase):
    def test_playing_the_open_games_pays_what_was_played_up_to_what_was_left(self):
        challenge = self.launch_debt(percent=40).json()["id"]
        self.played(self.ana, 3, game="alpha")  # of the 10 h left
        self.played(self.ana, 9, game="beta")  # of the 5 h left: pays 5
        part = self.part(challenge)
        self.assertEqual((part["initial_seconds"], part["paid_seconds"], part["percent"], part["done"]), (15 * HOUR, 8 * HOUR, 53.3, True))

    def test_new_games_neither_pay_nor_cost(self):
        challenge = self.launch_debt(percent=10).json()["id"]
        self.played(self.ana, 8, game="fresh")
        part = self.part(challenge)
        self.assertEqual((part["initial_seconds"], part["paid_seconds"], part["percent"], part["done"]), (15 * HOUR, 0, 0.0, False))

    def test_completing_a_game_pays_all_it_had_left(self):
        challenge = self.launch_debt(percent=30).json()["id"]
        self.played(self.ana, 1, game="alpha")
        self.complete(self.ana, "alpha")
        part = self.part(challenge)
        self.assertEqual((part["paid_seconds"], part["done"]), (10 * HOUR, True))  # 10 of 15 h, not just the hour played

    def test_abandoning_pays_nothing(self):
        challenge = self.launch_debt(percent=10).json()["id"]
        with database.SessionLocal() as db:
            db.execute(text("UPDATE users_games SET abandoned_at = :a WHERE game_id = 'alpha'"), {"a": datetime.datetime.now()})
            db.commit()
        self.assertEqual(self.part(challenge)["paid_seconds"], 0)

    def test_what_was_played_before_the_start_does_not_count_again(self):
        challenge = self.launch_debt(percent=10).json()["id"]
        self.assertEqual(self.part(challenge)["paid_seconds"], 0)  # the 10 h already in the games are what made the debt smaller already


class GamesTests(DebtTestCase):
    def test_closing_means_completing_one_of_the_games_that_were_open(self):
        challenge = self.launch_debt(mode="games", games=2).json()["id"]
        self.complete(self.ana, "alpha")
        self.played(self.ana, 1, game="fresh")
        self.complete(self.ana, "fresh")  # a new game: does not count
        part = self.part(challenge)
        self.assertEqual((part["count"], part["target_count"], part["done"]), (1, 2, False))
        self.complete(self.ana, "gamma")  # past its average time but open
        self.assertTrue(self.part(challenge)["done"])


class VisibilityTests(DebtTestCase):
    def test_others_see_it_and_only_its_owner_deletes_it(self):
        challenge = self.launch_debt().json()["id"]
        self.assertEqual(self.api("GET", f"/challenges/{challenge}", as_user="bea").json()["owner"]["name"], "Ana")
        self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user="bea").status_code, 403)
        self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user="ana").status_code, 200)

    def test_a_finished_one_is_in_the_history_of_its_owner(self):
        challenge = self.launch_debt(mode="games", games=1).json()["id"]
        self.complete(self.ana, "alpha")
        with database.SessionLocal() as db:
            db.execute(text("UPDATE challenges SET ends_on = :e WHERE id = :i"), {"e": TODAY() - timedelta(days=1), "i": challenge})
            db.commit()
        mine = self.api("GET", f"/challenges/player/{self.ana}", as_user="bea").json()
        self.assertEqual([(c["title"], c["scope"]) for c in mine], [("Cerrar 1 juego de la deuda", "user")])

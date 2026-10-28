"""Duels (1 vs 1) and the versus mode of the group challenges through real requests (MariaDB required, see
api_support.py): launching, who may decline and until when, the progress of both players and the history."""
from datetime import datetime, timedelta

from src.crud import challenges as crud
from src.database import database, models
from src.utils import challenges
from tests import clock, test_mariadb_api_challenges as base

TODAY = base.TODAY


class DuelTestCase(base.ChallengesTestCase):
    def launch_duel(self, kind="duel_hours", as_user="ana", **changes):
        options = {"opponent_id": self.bea, "duration": "week", **changes}
        return self.api("POST", "/challenges", as_user=as_user, json={"kind": kind, "options": options})

    def view(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()

    def backdate(self, challenge_id, days=0, launched_hours_ago=None):
        """Move the period back (a challenge always starts the day it is launched) and, if asked, its launch moment."""
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, challenge_id)
            row.starts_on = row.starts_on - timedelta(days=days)
            row.created_at = row.created_at - timedelta(days=days)
            if launched_hours_ago is not None:
                row.created_at = clock.now() - timedelta(hours=launched_hours_ago)
            db.commit()

    def play(self, user, game, days_ago, minutes):
        start = datetime.combine(TODAY() - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=12)
        if not self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u AND game_id = :g", u=user, g=game):
            self.library_entry(user, game, start.date(), "pc")
        self.session(user, game, start, minutes)


class LaunchTests(DuelTestCase):
    def test_a_player_challenges_another_and_it_starts_at_once(self):
        response = self.launch_duel()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["status"]), ("duel_hours", "duel", "Duelo de horas", "active"))
        self.assertEqual((body["owner"]["name"], body["opponent"]["name"], body["declined"]), ("Ana", "Bea", False))
        self.assertEqual(sorted(p["name"] for p in body["progress"]["players"]), ["Ana", "Bea"])
        self.assertEqual(self.scalar("SELECT owner_user_id FROM challenges"), self.ana)

    def test_a_duel_in_a_game_names_it(self):
        body = self.launch_duel("duel_game", game_id="hades").json()
        self.assertEqual((body["title"], body["game"]["id"]), ("Duelo en Hades", "hades"))
        self.assertEqual(self.launch_duel("duel_game", game_id="nope").status_code, 400)
        self.assertEqual(self.launch_duel("duel_game").status_code, 400)

    def test_the_opponent_must_be_another_active_player(self):
        for changes, fragment in (
            ({"opponent_id": self.ana}, "ti mismo"), ({"opponent_id": self.gone}, "activo"), ({"opponent_id": 9999}, "activo"),
            ({"opponent_id": None}, "retar"), ({"duration": "year"}, "duración"),
        ):
            response = self.launch_duel(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"], changes)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_an_equal_duel_is_refused_but_the_other_way_round_is_another(self):
        self.assertEqual(self.launch_duel().status_code, 201)
        self.assertEqual(self.launch_duel().status_code, 409)
        self.assertEqual(self.launch_duel(as_user="bea", opponent_id=self.ana).status_code, 201)

    def test_everybody_sees_it_but_only_the_challenger_deletes_it(self):
        challenge = self.launch_duel().json()["id"]
        self.assertEqual(self.api("GET", f"/challenges/{challenge}", as_user="root").status_code, 200)
        for user in ("bea", "root"):
            self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user=user).status_code, 403, user)
        self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user="ana").status_code, 200)


class ProgressTests(DuelTestCase):
    def test_hours_of_any_game_inside_the_period_decide_it(self):
        challenge = self.launch_duel().json()["id"]
        self.backdate(challenge, days=3)
        self.play(self.ana, "hades", 0, 120)
        self.play(self.ana, "celeste", 1, 60)
        self.play(self.bea, "hades", 2, 90)
        self.play(self.bea, "hades", 6, 600)  # before the period
        players = {p["name"]: (p["seconds"], p["position"], p["done"]) for p in self.view(challenge)["progress"]["players"]}
        self.assertEqual(players, {"Ana": (10800, 1, True), "Bea": (5400, 2, False)})

    def test_a_duel_in_a_game_counts_only_that_game(self):
        challenge = self.launch_duel("duel_game", game_id="hades").json()["id"]
        self.play(self.ana, "celeste", 0, 600)
        self.play(self.ana, "hades", 0, 30)
        self.play(self.bea, "hades", 0, 45)
        players = {p["name"]: (p["seconds"], p["done"]) for p in self.view(challenge)["progress"]["players"]}
        self.assertEqual(players, {"Ana": (1800, False), "Bea": (2700, True)})

    def test_nobody_wins_a_duel_nobody_played(self):
        body = self.view(self.launch_duel().json()["id"])
        self.assertEqual([p["done"] for p in body["progress"]["players"]], [False, False])


class DeclineTests(DuelTestCase):
    def decline(self, challenge, as_user="bea", joined=False):
        return self.api("PUT", f"/challenges/{challenge}/participation", as_user=as_user, params={"joined": joined})

    def test_only_the_challenged_player_can_decline_and_the_challenger_sees_it(self):
        challenge = self.launch_duel().json()["id"]
        self.assertTrue(self.view(challenge, "bea")["can_opt_out"])
        self.assertFalse(self.view(challenge, "ana")["can_opt_out"])
        for user in ("ana", "root"):
            self.assertEqual(self.decline(challenge, user).status_code, 409, user)
        body = self.decline(challenge).json()
        self.assertEqual((body["declined"], body["taking_part"], [p["name"] for p in body["progress"]["players"]]), (True, False, ["Ana"]))
        self.assertTrue(self.view(challenge, "ana")["declined"])

    def test_a_decline_is_final_and_a_duel_is_never_accepted_with_a_request(self):
        challenge = self.launch_duel().json()["id"]
        self.assertEqual(self.decline(challenge, joined=True).status_code, 409)  # it starts when launched: there is nothing to accept
        self.decline(challenge)
        self.assertEqual(self.decline(challenge, joined=True).status_code, 409)
        body = self.view(challenge, "bea")
        self.assertEqual((body["declined"], body["can_opt_out"], body["taking_part"]), (True, False, False))
        self.assertEqual(self.decline(challenge).status_code, 200)  # asking again changes nothing

    def test_after_two_days_the_duel_stands(self):
        challenge = self.launch_duel().json()["id"]
        self.backdate(challenge, launched_hours_ago=49)
        self.assertFalse(self.view(challenge, "bea")["can_opt_out"])
        self.assertEqual(self.decline(challenge).status_code, 409)
        self.backdate(challenge, launched_hours_ago=47)
        self.assertEqual(self.decline(challenge).status_code, 200)

    def test_a_declined_duel_is_nobodys_history(self):
        challenge = self.launch_duel().json()["id"]
        self.backdate(challenge, days=10)
        self.play(self.ana, "hades", 8, 60)
        self.decline(challenge)
        for player in (self.ana, self.bea):
            self.assertEqual(self.api("GET", f"/challenges/player/{player}", as_user="root").json(), [])


class HistoryTests(DuelTestCase):
    def finished(self, **plays):
        challenge = self.launch_duel().json()["id"]
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, challenge)
            row.starts_on, row.ends_on = TODAY() - timedelta(days=10), TODAY() - timedelta(days=3)
            row.created_at = datetime.combine(row.starts_on, datetime.min.time())
            db.commit()
        for user, minutes in plays.items():
            self.play(getattr(self, user), "hades", 5, minutes)
        return challenge

    def history(self, player):
        return self.api("GET", f"/challenges/player/{player}", as_user="root").json()

    def test_the_winner_and_the_loser_each_see_how_it_went(self):
        self.finished(ana=60, bea=30)
        won, lost = self.history(self.ana)[0], self.history(self.bea)[0]
        self.assertEqual((won["scope"], won["done"], won["tied"]), ("duel", True, False))
        self.assertEqual((lost["done"], lost["tied"]), (False, False))

    def test_the_history_can_start_from_a_year(self):
        self.finished(ana=60, bea=30)
        with database.SessionLocal() as db:
            self.assertEqual(len(crud.history(db, self.ana, TODAY(), TODAY().year)), 1)
            self.assertEqual(crud.history(db, self.ana, TODAY(), TODAY().year + 1), [])

    def test_a_tie_is_won_by_both(self):
        self.finished(ana=45, bea=45)
        self.assertEqual([(self.history(p)[0]["done"], self.history(p)[0]["tied"]) for p in (self.ana, self.bea)], [(True, True), (True, True)])


class GroupVersusTests(DuelTestCase):
    def test_a_group_challenge_can_rank_who_got_furthest(self):
        challenge = self.launch(versus=True).json()["id"]
        self.assertTrue(self.view(challenge)["params"]["versus"])
        self.play(self.ana, "hades", 0, 120)
        self.play(self.bea, "hades", 0, 60)
        positions = {p["name"]: (p["position"], p["winner"]) for p in self.view(challenge)["progress"]["players"]}
        self.assertEqual(positions, {"Ana": (1, True), "Bea": (2, False), "Root": (3, False)})

    def test_without_it_there_is_no_ranking(self):
        challenge = self.launch().json()["id"]
        self.assertNotIn("position", self.view(challenge)["progress"]["players"][0])

    def test_the_launch_notice_says_the_one_who_plays_most_wins(self):
        self.launch(versus=True)
        with database.SessionLocal() as db:
            self.assertIn("Gana quien más juegue", challenges.summary_game_of_month(db.query(models.Challenge).one()))

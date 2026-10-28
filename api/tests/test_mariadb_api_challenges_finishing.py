"""The challenges about finishing games and about the group's hours, through real requests (MariaDB required, see
api_support.py): finish what was started (`finish_backlog`), finish a game before starting another (`finish_first`),
the hours of the whole group (`group_hours`) and the duel of completed games (`duel_completed`)."""
from datetime import timedelta

from src.database import database, models
from tests import test_mariadb_api_challenges_duel as duels
from tests import test_mariadb_api_challenges_personal as personal

TODAY = personal.TODAY


class FinishingTestCase(personal.PersonalTestCase):
    def setUp(self):
        super().setUp()
        self.game("tetris", "Tetris")

    def open_game(self, user, game, days_ago=10):
        """A game started and not finished before a challenge launched `days_ago - 1` days back: a session of 30 minutes."""
        self.play(user, game, days_ago, 30)

    def complete(self, user, game, days_ago):
        with database.SessionLocal() as db:
            db.query(models.UserGame).filter_by(user_id=user, game_id=game).update({"completed": 1, "completed_date": TODAY() - timedelta(days=days_ago)})
            db.commit()

    def start(self, user, game, days_ago, platform="pc"):
        self.library_entry(user, game, TODAY() - timedelta(days=days_ago), platform)

    def launched(self, kind, back=5, **options):
        """A personal challenge launched `back` days ago (it always starts the day it is launched)."""
        response = self.launch_personal(kind, duration="month", **options)
        self.assertEqual(response.status_code, 201, response.text)
        self.backdate(response.json()["id"], back)
        return response.json()["id"]


class FinishBacklogTests(FinishingTestCase):
    def test_it_needs_a_game_started_and_not_finished(self):
        response = self.launch_personal("finish_backlog", games=1)
        self.assertEqual((response.status_code, response.json()["detail"]), (400, "No tienes juegos empezados y sin terminar"))
        self.play(self.ana, "hades", 3, 5)  # under 10 minutes: not started
        self.assertEqual(self.launch_personal("finish_backlog", games=1).status_code, 400)
        self.open_game(self.ana, "celeste")
        self.complete(self.ana, "celeste", 2)  # finished
        self.assertEqual(self.launch_personal("finish_backlog", games=1).status_code, 400)

    def test_a_game_without_an_average_time_is_as_open_as_any_other(self):
        self.open_game(self.ana, "hades")  # no avg_time: the debt would leave it out
        body = self.launch_personal("finish_backlog", games=1).json()
        self.assertEqual((body["title"], body["params"]), ("Terminar 1 juego empezado", {"games": 1, "duration": "month"}))

    def test_it_asks_for_no_more_games_than_are_open(self):
        self.open_game(self.ana, "hades")
        self.open_game(self.ana, "celeste")
        self.assertEqual(self.launch_personal("finish_backlog", games=3).status_code, 400)
        self.assertEqual(self.launch_personal("finish_backlog", games=0).status_code, 400)
        self.assertEqual(self.launch_personal("finish_backlog", games=2).json()["title"], "Terminar 2 juegos empezados")

    def test_only_a_completion_of_a_game_that_was_open_in_the_period_counts(self):
        self.open_game(self.ana, "hades")
        self.open_game(self.ana, "celeste")
        challenge = self.launched("finish_backlog", games=2)
        self.play(self.ana, "tetris", 3, 30)  # started after the launch
        self.complete(self.ana, "tetris", 2)
        self.assertEqual(self.part(challenge)["count"], 0)
        self.complete(self.ana, "hades", 1)
        part = self.part(challenge)
        self.assertEqual((part["count"], part["target_count"], part["unit"], part["done"]), (1, 2, "games", False))
        self.complete(self.ana, "celeste", 0)
        self.assertEqual(self.part(challenge)["done"], True)

    def test_a_game_finished_before_the_period_or_by_somebody_else_does_not_count(self):
        self.open_game(self.ana, "hades")
        self.open_game(self.bea, "hades")
        self.complete(self.bea, "hades", 1)
        challenge = self.launched("finish_backlog", games=1)
        self.assertEqual(self.part(challenge)["count"], 0)
        self.complete(self.ana, "hades", 8)  # before the challenge began (5 days back)
        self.assertEqual(self.part(challenge)["count"], 0)


class FinishFirstTests(FinishingTestCase):
    def test_it_needs_a_game_started_and_not_finished(self):
        response = self.launch_personal("finish_first")
        self.assertEqual(response.status_code, 400)
        self.assertIn("no hay nada que terminar", response.json()["detail"])

    def test_it_is_launched_with_only_a_duration(self):
        self.open_game(self.ana, "hades")
        body = self.launch_personal("finish_first", duration="week").json()
        self.assertEqual((body["title"], body["params"], body["scope"]), ("Terminar antes de empezar otro", {"duration": "week"}, "user"))
        player = body["progress"]["players"][0]
        self.assertEqual((player["count"], player["target_count"], player["done"], player["failed"]), (0, 1, False, False))

    def test_completing_an_open_game_wins_and_what_comes_after_changes_nothing(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first")
        self.complete(self.ana, "hades", 2)
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"], part["count"]), (True, False, 1))
        self.start(self.ana, "tetris", 1)  # a new game after the win
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"]), (True, False))

    def test_starting_a_new_game_first_loses_and_finishing_afterwards_does_not_undo_it(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first")
        self.start(self.ana, "tetris", 3)
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"], part["count"]), (False, True, 0))
        self.complete(self.ana, "hades", 1)
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"]), (False, True))

    def test_on_the_same_day_the_completion_comes_first(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first")
        self.start(self.ana, "tetris", 2)
        self.complete(self.ana, "hades", 2)
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"]), (True, False))

    def test_a_game_the_player_already_had_is_not_new_even_on_another_platform(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first")
        other = self.scalar("SELECT id FROM platform_tags WHERE id <> 'pc' LIMIT 1")
        self.start(self.ana, "hades", 3, platform=other)  # the same game, another platform
        self.start(self.ana, "celeste", 12)  # started before the challenge: not new either
        part = self.part(challenge)
        self.assertEqual((part["done"], part["failed"]), (False, False))

    def test_what_others_do_does_not_count(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first")
        self.start(self.bea, "tetris", 3)
        self.assertEqual(self.part(challenge)["failed"], False)

    def test_it_is_part_of_the_challenges_a_player_can_see_in_their_history_only_once_over(self):
        self.open_game(self.ana, "hades")
        challenge = self.launched("finish_first", back=0)
        self.assertEqual(self.api("GET", f"/challenges/player/{self.ana}", as_user="bea").json(), [])
        self.assertEqual(self.api("GET", f"/challenges/{challenge}", as_user="bea").status_code, 200)  # public, like the others


class GroupHoursTests(FinishingTestCase):
    def group_hours(self, **changes):
        return self.launch(kind="group_hours", **{"min_hours_total": 10, **changes})

    def view(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()

    def test_it_is_a_group_challenge_for_a_month_with_a_total_and_no_game(self):
        response = self.group_hours()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["game"], body["params"]), ("group_hours", "group", "Sumar 10 h entre todos", None, {"min_hours_total": 10.0}))
        self.assertEqual(sorted(p["name"] for p in body["progress"]["players"]), ["Ana", "Bea", "Root"])  # the inactive player is not there

    def test_the_options_are_checked(self):
        self.assertEqual(self.api("POST", "/manage/challenges", as_user="root", json={"kind": "group_hours", "month": self.options()["month"]}).status_code, 400)
        self.assertEqual(self.group_hours(min_hours_total=0.1).status_code, 400)
        self.assertEqual(self.group_hours(month="2020-01").status_code, 400)

    def test_players_can_neither_launch_it_nor_propose_it(self):
        self.assertEqual(self.api("POST", "/challenges", as_user="ana", json={"kind": "group_hours", "options": {"min_hours_total": 10}}).status_code, 403)
        proposal = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": "group_hours", "options": {"month": self.options()["month"], "min_hours_total": 10}})
        self.assertEqual(proposal.status_code, 400)

    def test_the_hours_of_everybody_add_up_whatever_the_game(self):
        challenge = self.group_hours().json()["id"]
        self.played(self.ana, 6, "hades")
        self.played(self.bea, 3, "celeste")
        self.played(self.gone, 50, "hades")  # inactive: never counted
        body = self.view(challenge)["progress"]
        self.assertEqual((body["total_seconds"], body["total_target_seconds"], body["total_done"]), (9 * 3600, 10 * 3600, False))
        self.assertEqual([p["done"] for p in body["players"]], [False, False, False])
        self.played(self.bea, 1, "hades")
        body = self.view(challenge)["progress"]
        self.assertEqual(body["total_done"], True)
        self.assertEqual({p["name"]: (p["seconds"], p["done"]) for p in body["players"]}, {"Ana": (6 * 3600, True), "Bea": (4 * 3600, True), "Root": (0, False)})
        self.assertTrue(all(p["contribution"] and p["target_seconds"] == 10 * 3600 for p in body["players"]))

    def test_a_session_of_another_month_does_not_count(self):
        challenge = self.group_hours().json()["id"]
        self.played(self.ana, 2, "hades", days_ago=60)
        self.assertEqual(self.view(challenge)["progress"]["total_seconds"], 0)

    def test_as_a_contest_it_ranks_who_put_in_more(self):
        challenge = self.group_hours(versus=True).json()["id"]
        self.played(self.ana, 1, "hades")
        self.played(self.bea, 3, "celeste")
        players = self.view(challenge)["progress"]["players"]
        self.assertEqual([(p["name"], p["position"], p["winner"]) for p in players], [("Bea", 1, True), ("Ana", 2, False), ("Root", 3, False)])

    def test_a_voluntary_one_counts_only_who_joined(self):
        challenge = self.group_hours(participation="opt_in").json()["id"]
        self.api("PUT", f"/challenges/{challenge}/participation", as_user="ana", params={"joined": True})
        self.played(self.ana, 2, "hades")
        self.played(self.bea, 5, "hades")
        progress = self.view(challenge)["progress"]
        self.assertEqual(([p["name"] for p in progress["players"]], progress["total_seconds"]), (["Ana"], 2 * 3600))


class DuelCompletedTests(FinishingTestCase, duels.DuelTestCase):
    def test_it_is_a_duel_like_the_others(self):
        body = self.launch_duel("duel_completed").json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["status"]), ("duel_completed", "duel", "Duelo de completados", "active"))
        self.assertEqual((body["owner"]["name"], body["opponent"]["name"]), ("Ana", "Bea"))
        self.assertEqual(self.launch_duel("duel_completed", opponent_id=self.ana).status_code, 400)
        self.assertEqual(self.launch_duel("duel_completed").status_code, 409)  # the same duel again

    def test_whoever_completes_more_games_in_the_period_wins(self):
        for game in ("hades", "celeste", "tetris"):
            self.open_game(self.ana, game)
        self.open_game(self.bea, "hades")
        duel = self.launch_duel("duel_completed").json()["id"]
        self.backdate(duel, 5)
        self.complete(self.ana, "hades", 1)
        self.complete(self.ana, "celeste", 2)
        self.complete(self.bea, "hades", 3)
        players = self.view(duel)["progress"]["players"]
        self.assertEqual([(p["name"], p["count"], p["target_count"], p["unit"], p["position"], p["done"]) for p in players],
                         [("Ana", 2, 2, "games", 1, True), ("Bea", 1, 2, "games", 2, False)])
        self.assertNotIn("seconds", players[0])

    def test_a_completion_before_the_duel_does_not_count_and_a_tie_is_won_by_both(self):
        for user in (self.ana, self.bea):
            self.open_game(user, "hades")
            self.open_game(user, "celeste")
        duel = self.launch_duel("duel_completed").json()["id"]
        self.backdate(duel, 5)
        self.complete(self.ana, "hades", 9)  # before it began
        self.assertEqual([(p["count"], p["done"]) for p in self.view(duel)["progress"]["players"]], [(0, False), (0, False)])
        self.complete(self.ana, "celeste", 1)
        self.complete(self.bea, "celeste", 2)
        self.assertEqual([(p["count"], p["done"]) for p in self.view(duel)["progress"]["players"]], [(1, True), (1, True)])

    def test_a_declined_duel_is_not_won_by_the_challenger(self):
        self.open_game(self.ana, "hades")
        duel = self.launch_duel("duel_completed").json()["id"]
        self.api("PUT", f"/challenges/{duel}/participation", as_user="bea", params={"joined": False})  # inside the first 48 hours
        self.backdate(duel, 5)
        self.complete(self.ana, "hades", 1)
        view = self.view(duel)
        self.assertEqual((view["declined"], [p["name"] for p in view["progress"]["players"]]), (True, ["Ana"]))

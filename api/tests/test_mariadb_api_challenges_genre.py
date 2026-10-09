"""The "try a genre" challenge, the first personal one, through real requests (MariaDB required, see api_support.py):
launching it, its options and duplicates, who sees and deletes it, and what counts for its progress."""
import asyncio
from datetime import timedelta

from sqlalchemy import text

from src.database import database
from src.utils import actions
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY


class NewGenreTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.game("dead-cells", "Dead Cells", genres="Action, Metroidvania")
        self.game("hollow", "Hollow Knight", genres="Metroidvania,Indie")
        self.game("tetris", "Tetris", genres="Puzzle")
        self.game("hades-2", "Hades II", genres="Action,Roguelike")

    def launch_genre(self, as_user="ana", **changes):
        options = {"genre": "Metroidvania", "mode": "play", "hours": 2, "duration": "month", **changes}
        return self.api("POST", "/challenges", as_user=as_user, json={"kind": "new_genre", "options": options})

    def progress(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()["progress"]["players"][0]


class LaunchTests(NewGenreTestCase):
    def test_the_genres_are_those_of_the_games_with_whether_the_caller_has_one(self):
        self.library_entry(self.ana, "tetris", TODAY(), "pc")
        body = self.api("GET", "/challenges/genres", as_user="ana").json()
        self.assertEqual(
            {g["genre"]: (g["games"], g["played"]) for g in body},
            {"Action": (2, False), "Metroidvania": (2, False), "Indie": (1, False), "Puzzle": (1, True), "Roguelike": (1, False)},
        )

    def test_the_templates_say_a_player_may_launch_this_one_from_the_page(self):
        body = self.api("GET", "/challenges/templates", as_user="ana").json()
        self.assertEqual({t["kind"]: (t["scope"], t["can_launch"]) for t in body}, {"game_of_month": ("group", False), "themed": ("group", False), "new_genre": ("user", True)})

    def test_a_player_launches_a_personal_challenge_that_starts_today(self):
        response = self.launch_genre()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["status"]), ("new_genre", "user", "Probar un género: Metroidvania", "active"))
        self.assertEqual((body["starts_on"], body["ends_on"]), (TODAY().isoformat(), (TODAY() + timedelta(days=29)).isoformat()))  # 30 days counting today
        self.assertEqual((body["owner"]["name"], body["params"]), ("Ana", {"genre": "Metroidvania", "mode": "play", "duration": "month", "hours": 2.0}))
        self.assertEqual((body["taking_part"], body["can_opt_out"]), (True, False))
        self.assertEqual(self.scalar("SELECT owner_user_id FROM challenges"), self.ana)

    def test_the_defaults_are_two_hours_and_a_month_and_a_completion_has_no_hours(self):
        sent = {"kind": "new_genre", "options": {"genre": "metroidvania", "mode": "play"}}
        body = self.api("POST", "/challenges", as_user="ana", json=sent).json()
        self.assertEqual(body["params"], {"genre": "Metroidvania", "mode": "play", "duration": "month", "hours": 2.0})  # the genre as the database writes it
        done = self.launch_genre(mode="complete", hours=99, duration="week").json()
        self.assertEqual(done["params"], {"genre": "Metroidvania", "mode": "complete", "duration": "week"})
        self.assertEqual(done["ends_on"], (TODAY() + timedelta(days=6)).isoformat())

    def test_the_options_are_checked(self):
        for changes, fragment in (
            ({"genre": "Nope"}, "género"), ({"genre": ""}, "género"), ({"mode": "win"}, "jugar o completar"),
            ({"duration": "year"}, "duración"), ({"hours": 0}, "horas"), ({"hours": "abc"}, "número"),
        ):
            response = self.launch_genre(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_an_equal_challenge_of_the_same_player_is_refused_but_another_player_may_have_it(self):
        self.assertEqual(self.launch_genre().status_code, 201)
        self.assertEqual(self.launch_genre().status_code, 409)
        self.assertEqual(self.launch_genre(hours=3).status_code, 201)
        self.assertEqual(self.launch_genre(as_user="bea").status_code, 201)

    def test_everybody_sees_it_but_only_the_owner_takes_part_and_deletes_it(self):
        challenge = self.launch_genre().json()["id"]
        seen = self.api("GET", f"/challenges/{challenge}", as_user="bea").json()
        self.assertEqual((seen["taking_part"], seen["owner"]["name"]), (False, "Ana"))
        self.assertEqual(self.api("PUT", f"/challenges/{challenge}/participation", as_user="ana", params={"joined": False}).status_code, 409)
        for user in ("bea", "root"):
            self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user=user).status_code, 403, user)
        self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user="ana").status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_an_admin_sees_it_in_the_panel(self):
        self.launch_genre()
        rows = self.api("GET", "/manage/challenges", as_user="root").json()
        self.assertEqual([(r["scope"], r["owner"], r["players"]) for r in rows], [("user", "Ana", 1)])


class ProgressTests(NewGenreTestCase):
    def test_only_new_games_of_the_genre_played_from_the_start_count(self):
        self.library_entry(self.ana, "hollow", TODAY() - timedelta(days=100), "pc")  # had it before: does not count
        challenge = self.launch_genre().json()["id"]
        self.played(self.ana, 1.5, game="dead-cells")
        self.played(self.ana, 1, game="hollow")
        self.played(self.ana, 4, game="tetris")  # another genre
        self.played(self.bea, 3, game="dead-cells")  # another player
        player = self.progress(challenge)
        self.assertEqual((player["seconds"], player["target_seconds"], player["done"]), (5400, 7200, False))
        self.played(self.ana, 1, game="dead-cells")
        self.assertTrue(self.progress(challenge)["done"])

    def test_a_session_before_the_period_does_not_count(self):
        challenge = self.launch_genre().json()["id"]
        self.library_entry(self.ana, "dead-cells", TODAY() - timedelta(days=3), "pc")
        self.played(self.ana, 5, game="dead-cells", days_ago=3)
        self.assertEqual(self.progress(challenge)["seconds"], 0)

    def test_completing_a_new_game_of_the_genre_in_the_period_is_what_complete_asks(self):
        self.library_entry(self.ana, "hollow", TODAY() - timedelta(days=100), "pc", completed=1, completed_date=TODAY() - timedelta(days=90))
        challenge = self.launch_genre(mode="complete").json()["id"]
        self.assertEqual(self.progress(challenge), {"user_id": self.ana, "name": "Ana", "count": 0, "target_count": 1, "done": False})
        self.library_entry(self.ana, "tetris", TODAY(), "pc", completed=1, completed_date=TODAY())  # another genre
        self.assertFalse(self.progress(challenge)["done"])
        self.library_entry(self.ana, "dead-cells", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.assertEqual((self.progress(challenge)["count"], self.progress(challenge)["done"]), (1, True))

    def test_a_finished_challenge_is_in_the_history_of_its_owner_only(self):
        challenge = self.launch_genre().json()["id"]
        with database.SessionLocal() as db:
            db.execute(text("UPDATE challenges SET starts_on = :s, ends_on = :e WHERE id = :i"),
                       {"s": TODAY() - timedelta(days=40), "e": TODAY() - timedelta(days=10), "i": challenge})
            db.commit()
        mine = self.api("GET", f"/challenges/player/{self.ana}", as_user="bea").json()
        self.assertEqual([(c["title"], c["scope"], c["done"]) for c in mine], [("Probar un género: Metroidvania", "user", False)])
        self.assertEqual(self.api("GET", f"/challenges/player/{self.bea}", as_user="bea").json(), [])

    def test_no_notice_is_sent_for_a_personal_challenge(self):
        self.launch_genre()
        self.played(self.ana, 5, game="dead-cells")
        with database.SessionLocal() as db:
            self.assertEqual(asyncio.run(actions.announce_challenge_totals(db)), 0)

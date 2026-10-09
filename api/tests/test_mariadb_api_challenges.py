"""The challenges through real requests (MariaDB required, see api_support.py): who may launch what, the options and
duplicates, taking part, the progress and the history, and the notices of the launch and of the total reached."""
import asyncio
import datetime
from datetime import timedelta
from unittest import mock

from sqlalchemy import text

from src.database import database, models
from src.utils import actions, my_utils
from tests import clock
from tests.api_support import ApiTestCase

TODAY = clock.today


def this_month(today=None):
    today = today or TODAY()
    return f"{today.year:04d}-{today.month:02d}"


class ChallengesTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.user("root", admin=True)
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.gone = self.user("gone", active=False)
        self.game("hades", "Hades")
        self.game("celeste", "Celeste")

    def options(self, **changes):
        return {"game_id": "hades", "month": this_month(), "min_hours_each": 5, "min_hours_total": 12, **changes}

    def launch(self, as_user="root", kind="game_of_month", announce=False, **changes):
        """A group challenge, launched from the admin panel's route (the only one that makes them)."""
        return self.api("POST", "/manage/challenges", as_user=as_user, json={"kind": kind, **self.options(**changes), "announce": announce})

    def played(self, user, hours, game="hades", days_ago=0):
        start = clock.now() - timedelta(days=days_ago, hours=hours + 1)
        if not self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u AND game_id = :g", u=user, g=game):
            self.library_entry(user, game, start.date(), "pc")
        self.session(user, game, start, int(hours * 60))


class LaunchTests(ChallengesTestCase):
    def test_everything_needs_a_login(self):
        for method, path in (("GET", "/challenges"), ("GET", "/challenges/1"), ("POST", "/challenges"), ("GET", "/challenges/templates"), ("DELETE", "/challenges/1")):
            self.assertEqual(self.api(method, path).status_code, 401, path)

    def test_the_templates_say_the_group_ones_are_not_launched_from_the_challenges_page(self):
        for user in ("root", "ana"):  # not even an admin
            body = self.api("GET", "/challenges/templates", as_user=user).json()
            self.assertEqual([(t["scope"], t["can_launch"]) for t in body if t["kind"] == "game_of_month"], [("group", False)])

    def test_an_admin_launches_a_game_of_the_month_for_the_group(self):
        response = self.launch()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["status"]), ("game_of_month", "group", "Juego del mes: Hades", "active"))
        self.assertEqual((body["game"]["id"], body["params"]), ("hades", {"min_hours_each": 5.0, "min_hours_total": 12.0}))
        self.assertEqual([p["name"] for p in body["progress"]["players"]], ["Ana", "Bea", "Root"])  # the active ones; Gone is inactive

    def test_a_player_cannot_launch_a_group_challenge(self):
        self.assertEqual(self.launch(as_user="ana").status_code, 403)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_the_challenges_route_never_makes_a_group_challenge_not_even_for_an_admin(self):
        for user in ("root", "ana"):
            response = self.api("POST", "/challenges", as_user=user, json={"kind": "game_of_month", "options": self.options()})
            self.assertEqual(response.status_code, 403, user)
            self.assertIn("panel de administración", response.json()["detail"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_a_group_template_is_the_only_kind_the_panel_launches(self):
        self.assertEqual(self.launch(kind="nope").status_code, 400)
        self.assertEqual(self.api("POST", "/manage/challenges", as_user="root", json={}).status_code, 400)  # no game: the options are checked

    def test_the_options_are_checked(self):
        past = f"{TODAY().year - 1:04d}-01"
        for changes, fragment in (
            ({"game_id": "nope"}, "juego"),
            ({"month": "2026-13"}, "mes"),
            ({"month": past}, "ya ha pasado"),
            ({"min_hours_each": 0}, "mínimo"),
            ({"min_hours_total": 3, "min_hours_each": 5}, "no puede ser menor"),
        ):
            response = self.launch(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        self.assertEqual(self.launch(min_hours_each="abc").status_code, 422)  # not even a number
        self.assertEqual(self.api("POST", "/challenges", as_user="root", json={"kind": "nope", "options": {}}).status_code, 400)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_what_the_panel_launches_is_in_the_audit_log(self):
        challenge = self.launch().json()["id"]
        rows = self.api("GET", "/manage/audit", as_user="root", params={"entity": "challenges"}).json()["items"]
        self.assertEqual([(r["method"], r["username"]) for r in rows], [("POST", "root")])

    def test_an_equal_challenge_is_refused_but_a_different_one_is_not(self):
        self.assertEqual(self.launch().status_code, 201)
        again = self.launch()
        self.assertEqual((again.status_code, again.json()["detail"]), (409, "Ya existe un reto igual"))
        self.assertEqual(self.launch(min_hours_each=6).status_code, 201)
        self.assertEqual(self.launch(game_id="celeste").status_code, 201)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 3)

    def test_the_group_is_told_only_when_the_admin_chooses_to(self):
        self.launch(announce=False)
        self.background["after_challenge_launch"].assert_not_called()
        self.launch(announce=True, min_hours_each=6)
        self.background["after_challenge_launch"].assert_called_once()


class ParticipationTests(ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.challenge = self.launch().json()["id"]

    def players(self, as_user="ana"):
        return [p["name"] for p in self.api("GET", f"/challenges/{self.challenge}", as_user=as_user).json()["progress"]["players"]]

    def test_a_player_can_leave_and_come_back(self):
        left = self.api("PUT", f"/challenges/{self.challenge}/participation", as_user="ana", params={"joined": False}).json()
        self.assertEqual((left["taking_part"], self.players()), (False, ["Bea", "Root"]))
        again = self.api("PUT", f"/challenges/{self.challenge}/participation", as_user="ana", params={"joined": True}).json()
        self.assertEqual((again["taking_part"], self.players()), (True, ["Ana", "Bea", "Root"]))

    def test_asking_twice_changes_nothing(self):
        for _ in range(2):
            self.api("PUT", f"/challenges/{self.challenge}/participation", as_user="ana", params={"joined": False})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_optouts"), 1)

    def test_it_is_about_the_caller_only_and_not_after_the_end(self):
        self.api("PUT", f"/challenges/{self.challenge}/participation", as_user="ana", params={"joined": False})
        self.assertEqual(self.players(as_user="bea"), ["Bea", "Root"])
        with database.SessionLocal() as db:
            db.execute(text("UPDATE challenges SET starts_on = :s, ends_on = :e"), {"s": TODAY() - timedelta(days=40), "e": TODAY() - timedelta(days=10)})
            db.commit()
        late = self.api("PUT", f"/challenges/{self.challenge}/participation", as_user="bea", params={"joined": False})
        self.assertEqual(late.status_code, 409)


class ProgressTests(ChallengesTestCase):
    def test_the_hours_of_each_player_in_that_game_within_the_month_count(self):
        challenge = self.launch().json()["id"]
        self.played(self.ana, 6)
        self.played(self.bea, 2)
        self.played(self.bea, 3, game="celeste")  # another game
        body = self.api("GET", f"/challenges/{challenge}", as_user="bea").json()
        players = {p["name"]: (p["seconds"], p["done"]) for p in body["progress"]["players"]}
        self.assertEqual(players, {"Ana": (6 * 3600, True), "Bea": (2 * 3600, False), "Root": (0, False)})
        self.assertEqual((body["progress"]["total_seconds"], body["progress"]["total_done"]), (8 * 3600, False))

    def test_a_session_outside_the_period_does_not_count(self):
        challenge = self.launch(month=this_month(TODAY() + timedelta(days=40))).json()["id"]
        self.played(self.ana, 6)
        body = self.api("GET", f"/challenges/{challenge}", as_user="ana").json()
        self.assertEqual(body["status"], "upcoming")
        self.assertEqual(body["progress"]["total_seconds"], 0)

    def test_the_list_has_every_challenge_with_its_progress(self):
        self.launch()
        self.launch(game_id="celeste")
        body = self.api("GET", "/challenges", as_user="ana").json()
        self.assertEqual(sorted(c["title"] for c in body), ["Juego del mes: Celeste", "Juego del mes: Hades"])
        self.assertTrue(all("progress" in c and c["taking_part"] for c in body))

    def test_an_unknown_challenge_is_a_404(self):
        self.assertEqual(self.api("GET", "/challenges/999", as_user="ana").status_code, 404)


class DeleteTests(ChallengesTestCase):
    def test_a_group_challenge_is_deleted_from_the_panel_only(self):
        challenge = self.launch().json()["id"]
        for user in ("ana", "root"):  # the challenges route is for one's own, personal challenges
            self.assertEqual(self.api("DELETE", f"/challenges/{challenge}", as_user=user).status_code, 403, user)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 1)
        self.assertEqual(self.api("DELETE", f"/manage/challenges/{challenge}", as_user="root").status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_deleting_the_game_or_the_challenge_takes_the_rest_with_it(self):
        challenge = self.launch().json()["id"]
        self.api("PUT", f"/challenges/{challenge}/participation", as_user="ana", params={"joined": False})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_optouts"), 1)
        self.api("DELETE", "/manage/games/hades", as_user="root")
        self.assertEqual((self.scalar("SELECT COUNT(*) FROM challenges"), self.scalar("SELECT COUNT(*) FROM challenge_optouts")), (0, 0))


class HistoryTests(ChallengesTestCase):
    def finished(self, challenge_id):
        with database.SessionLocal() as db:
            db.execute(text("UPDATE challenges SET starts_on = :s, ends_on = :e WHERE id = :i"),
                       {"s": TODAY() - timedelta(days=40), "e": TODAY() - timedelta(days=10), "i": challenge_id})
            db.commit()

    def test_a_finished_challenge_is_in_the_history_of_the_ones_who_took_part(self):
        challenge = self.launch().json()["id"]
        self.played(self.ana, 6, days_ago=20)
        self.finished(challenge)
        mine = self.api("GET", f"/challenges/player/{self.ana}", as_user="bea").json()
        self.assertEqual([(c["title"], c["done"]) for c in mine], [("Juego del mes: Hades", True)])
        theirs = self.api("GET", f"/challenges/player/{self.bea}", as_user="ana").json()
        self.assertEqual([(c["title"], c["done"]) for c in theirs], [("Juego del mes: Hades", False)])

    def test_a_running_challenge_is_not_history_yet_and_neither_is_one_you_left(self):
        running = self.launch().json()["id"]
        self.assertEqual(self.api("GET", f"/challenges/player/{self.ana}", as_user="ana").json(), [])
        self.finished(running)
        self.assertEqual(len(self.api("GET", f"/challenges/player/{self.ana}", as_user="ana").json()), 1)
        with database.SessionLocal() as db:
            db.add(models.ChallengeOptOut(challenge_id=running, user_id=self.ana))
            db.commit()
        self.assertEqual(self.api("GET", f"/challenges/player/{self.ana}", as_user="ana").json(), [])

    def test_an_unknown_player_is_a_404(self):
        self.assertEqual(self.api("GET", "/challenges/player/99999", as_user="ana").status_code, 404)


class NoticeTests(ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.sent = []

        async def send(msg, silent, *args, **kwargs):
            self.sent.append(msg)

        patcher = mock.patch.object(my_utils, "send_message", new=send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_the_launch_notice_says_what_is_asked(self):
        challenge = self.launch().json()["id"]
        with database.SessionLocal() as db:
            self.run_async(actions.announce_challenge_launch(db, challenge))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Nuevo reto del grupo", self.sent[0])
        self.assertIn("Juego del mes: Hades", self.sent[0])
        self.assertIn("Mínimo 5 h cada uno y 12 h entre todos", self.sent[0])

    def test_the_group_hears_that_the_total_was_reached_once(self):
        self.launch()
        with database.SessionLocal() as db:
            self.assertEqual(self.run_async(actions.announce_challenge_totals(db)), 0)  # nobody has played
        self.played(self.ana, 7)
        self.played(self.bea, 6)
        with database.SessionLocal() as db:
            self.assertEqual(self.run_async(actions.announce_challenge_totals(db)), 1)
            self.assertEqual(self.run_async(actions.announce_challenge_totals(db)), 0)  # already said
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Reto cumplido", self.sent[0])
        self.assertIn("2 de 3 ya habéis cumplido", self.sent[0])
        self.assertIsNotNone(self.scalar("SELECT total_notified_at FROM challenges"))

    def test_a_challenge_that_has_ended_is_not_announced_any_more(self):
        challenge = self.launch().json()["id"]
        self.played(self.ana, 14, days_ago=20)
        with database.SessionLocal() as db:
            db.execute(text("UPDATE challenges SET starts_on = :s, ends_on = :e WHERE id = :i"),
                       {"s": TODAY() - timedelta(days=40), "e": TODAY() - timedelta(days=10), "i": challenge})
            db.commit()
            self.assertEqual(self.run_async(actions.announce_challenge_totals(db)), 0)


class AdminPanelTests(ChallengesTestCase):
    def test_the_panel_lists_every_challenge_and_deletes_one(self):
        challenge = self.launch().json()["id"]
        rows = self.api("GET", "/manage/challenges", as_user="root").json()
        self.assertEqual([(r["id"], r["title"], r["scope"], r["status"], r["players"], r["created_by"]) for r in rows],
                         [(challenge, "Juego del mes: Hades", "group", "active", 3, "root")])
        self.assertEqual(self.api("GET", "/manage/challenges", as_user="ana").status_code, 403)
        self.assertEqual(self.api("DELETE", f"/manage/challenges/{challenge}", as_user="ana").status_code, 403)
        self.assertEqual(self.api("DELETE", f"/manage/challenges/{challenge}", as_user="root").status_code, 200)
        self.assertEqual(self.api("DELETE", f"/manage/challenges/{challenge}", as_user="root").status_code, 404)

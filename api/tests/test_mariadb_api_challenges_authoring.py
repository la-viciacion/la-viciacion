"""Who authors the group challenges, through real requests (MariaDB required, see api_support.py): the voluntary ones
(only who joins takes part), the proposals of the players that an admin decides, and the schedules that launch a
challenge every month."""
import asyncio
import json
from datetime import timedelta
from unittest import mock

from src.crud import challenge_schedules
from src.database import database, models
from src.utils import actions, challenges, my_utils
from tests import clock
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY


class AuthoringTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.game("dead-cells", "Dead Cells", tags="Singleplayer, Horror")
        self.game("tetris", "Tetris", tags="Puzzle")

    def view(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()

    def join(self, challenge_id, as_user="ana", joined=True):
        return self.api("PUT", f"/challenges/{challenge_id}/participation", as_user=as_user, params={"joined": joined})

    def players(self, challenge_id, as_user="ana"):
        return sorted(p["name"] for p in self.view(challenge_id, as_user)["progress"]["players"])


class VoluntaryTests(AuthoringTestCase):
    def test_nobody_takes_part_in_a_voluntary_challenge_until_they_join(self):
        challenge = self.launch(participation="opt_in")
        self.assertEqual(challenge.status_code, 201)
        body = challenge.json()
        self.assertEqual((body["participation"], body["taking_part"], body["can_opt_out"]), ("opt_in", False, True))
        self.assertEqual(self.players(body["id"]), [])
        self.assertFalse(body["progress"]["total_done"])

    def test_a_player_joins_and_leaves_and_asking_twice_changes_nothing(self):
        challenge = self.launch(participation="opt_in").json()["id"]
        for _ in range(2):
            self.assertTrue(self.join(challenge).json()["taking_part"])
        self.assertEqual(self.players(challenge), ["Ana"])
        self.join(challenge, "bea")
        self.assertEqual(self.players(challenge), ["Ana", "Bea"])
        for _ in range(2):
            self.assertFalse(self.join(challenge, joined=False).json()["taking_part"])
        self.assertEqual(self.players(challenge), ["Bea"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_optouts"), 1)  # the row is "joined" here

    def test_only_who_joined_counts_and_the_inactive_never_do(self):
        challenge = self.launch(participation="opt_in", min_hours_each=1, min_hours_total=2).json()["id"]
        self.join(challenge)
        self.played(self.ana, 2)
        self.played(self.bea, 5)  # did not join: nothing counts
        body = self.view(challenge)
        self.assertEqual([(p["name"], p["done"]) for p in body["progress"]["players"]], [("Ana", True)])
        self.assertEqual((body["progress"]["total_seconds"], body["progress"]["total_done"]), (2 * 3600, True))
        with database.SessionLocal() as db:
            db.add(models.ChallengeOptOut(challenge_id=challenge, user_id=self.gone))
            db.commit()
        self.assertEqual(self.players(challenge), ["Ana"])

    def test_a_challenge_that_everybody_takes_part_in_is_the_default_and_leaving_is_still_a_row(self):
        challenge = self.launch().json()
        self.assertEqual(challenge["participation"], "auto")
        self.assertEqual(self.players(challenge["id"]), ["Ana", "Bea", "Root"])
        self.join(challenge["id"], joined=False)
        self.assertEqual(self.players(challenge["id"]), ["Bea", "Root"])

    def test_the_same_challenge_voluntary_and_for_everybody_are_two_challenges(self):
        self.assertEqual(self.launch().status_code, 201)
        self.assertEqual(self.launch().status_code, 409)
        self.assertEqual(self.launch(participation="opt_in").status_code, 201)
        self.assertEqual(self.launch(participation="opt_in").status_code, 409)

    def test_the_participation_is_checked(self):
        response = self.launch(participation="maybe")
        self.assertEqual(response.status_code, 400)
        self.assertIn("voluntaria", response.json()["detail"])

    def test_a_voluntary_challenge_is_in_the_history_of_who_joined_only(self):
        challenge = self.launch(participation="opt_in").json()["id"]
        self.join(challenge)
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, challenge)
            row.starts_on, row.ends_on = TODAY() - timedelta(days=30), TODAY() - timedelta(days=2)
            db.commit()
        self.assertEqual(len(self.api("GET", f"/challenges/player/{self.ana}", as_user="ana").json()), 1)
        self.assertEqual(self.api("GET", f"/challenges/player/{self.bea}", as_user="ana").json(), [])

    def test_the_panel_says_how_each_one_takes_part(self):
        self.launch(participation="opt_in")
        self.assertEqual([r["participation"] for r in self.api("GET", "/manage/challenges", as_user="root").json()], ["opt_in"])

    def test_the_launch_notice_asks_to_join(self):
        sent = []

        async def send(msg, silent, *args, **kwargs):
            sent.append(msg)

        challenge = self.launch(participation="opt_in").json()["id"]
        with mock.patch.object(my_utils, "send_message", new=send), database.SessionLocal() as db:
            asyncio.run(actions.announce_challenge_launch(db, challenge))
        self.assertIn("Es voluntario: apúntate en Retos", sent[0])


class ProposalTestCase(AuthoringTestCase):
    def propose(self, as_user="ana", kind="game_of_month", **changes):
        options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10, **changes}
        return self.api("POST", "/challenges/proposals", as_user=as_user, json={"kind": kind, "options": options})

    def themed(self, as_user="ana", **changes):
        return self.propose(as_user, "themed", game_id=None, min_hours_total=None, theme="Terror", mode="play", **changes)

    def decide(self, proposal, action, as_user="root", **body):
        return self.api("POST", f"/manage/challenge-proposals/{proposal}/{action}", as_user=as_user, json={"announce": False, **body})


class ProposeTests(ProposalTestCase):
    def test_a_player_proposes_a_challenge_and_only_they_see_it(self):
        response = self.propose()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["status"], body["title"], body["proposer"]["name"], body["challenge_id"]), ("pending", "Juego del mes: Hades", "Ana", None))
        self.assertEqual([p["id"] for p in self.api("GET", "/challenges/proposals", as_user="ana").json()], [body["id"]])
        self.assertEqual(self.api("GET", "/challenges/proposals", as_user="bea").json(), [])
        self.assertEqual(self.api("GET", "/challenges", as_user="bea").json(), [])  # not a challenge yet

    def test_a_themed_one_can_be_proposed_with_the_themes_that_have_games(self):
        themes = self.api("GET", "/challenges/themes", as_user="ana").json()
        self.assertEqual(themes, [{"theme": "Terror", "games": 1}])  # Singleplayer and Puzzle are no theme
        self.assertEqual(self.themed().json()["title"], "Temático: Terror")

    def test_the_options_are_checked_like_a_launch(self):
        for changes, kind, fragment in (
            ({"game_id": "nope"}, "game_of_month", "juego"), ({"month": "2020-01"}, "game_of_month", "pasado"),
            ({"min_hours_total": 1}, "game_of_month", "total"), ({"theme": "Nope"}, "themed", "temática"),
        ):
            options = {"game_id": "hades", "month": base.this_month(), "min_hours_each": 3, "min_hours_total": 10, "theme": "Terror", "mode": "play", **changes}
            response = self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": kind, "options": options})
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        for kind in ("duel_hours", "streak", "nope"):
            self.assertEqual(self.api("POST", "/challenges/proposals", as_user="ana", json={"kind": kind, "options": {}}).status_code, 400, kind)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_proposals"), 0)

    def test_what_a_template_does_not_know_is_not_kept(self):
        self.propose(owner_user_id=5, participation="opt_in")
        self.assertEqual(sorted(json.loads(self.scalar("SELECT options FROM challenge_proposals"))), ["game_id", "min_hours_each", "min_hours_total", "month"])

    def test_a_player_has_at_most_three_waiting(self):
        for game in ("hades", "celeste", "dead-cells"):
            self.assertEqual(self.propose(game_id=game).status_code, 201)
        response = self.propose(game_id="tetris")
        self.assertEqual(response.status_code, 409)
        self.assertIn("3 propuestas pendientes", response.json()["detail"])
        self.assertEqual(self.propose(as_user="bea", game_id="tetris").status_code, 201)  # the limit is per player

    def test_an_equal_challenge_or_an_equal_waiting_proposal_is_refused(self):
        self.assertEqual(self.propose().status_code, 201)
        again = self.propose(as_user="bea")
        self.assertEqual((again.status_code, again.json()["detail"]), (409, "Ya hay una propuesta igual esperando respuesta"))
        self.launch(game_id="celeste", min_hours_each=3, min_hours_total=10)
        existing = self.propose(game_id="celeste")
        self.assertEqual((existing.status_code, existing.json()["detail"]), (409, "Ya existe un reto igual"))

    def test_a_proposal_is_withdrawn_by_its_proposer_while_it_waits(self):
        proposal = self.propose().json()["id"]
        self.assertEqual(self.api("DELETE", f"/challenges/proposals/{proposal}", as_user="bea").status_code, 404)
        self.assertEqual(self.api("DELETE", f"/challenges/proposals/{proposal}", as_user="ana").status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_proposals"), 0)
        decided = self.propose().json()["id"]
        self.decide(decided, "reject")
        self.assertEqual(self.api("DELETE", f"/challenges/proposals/{decided}", as_user="ana").status_code, 409)

    def test_everything_needs_a_login(self):
        for method, path in (("GET", "/challenges/proposals"), ("POST", "/challenges/proposals"), ("DELETE", "/challenges/proposals/1"), ("GET", "/challenges/tags")):
            self.assertIn(self.api(method, path, json={} if method == "POST" else None).status_code, (401, 403), path)


class DecisionTests(ProposalTestCase):
    def test_an_admin_sees_them_with_the_waiting_ones_first(self):
        first = self.propose().json()["id"]
        second = self.propose(as_user="bea", game_id="celeste").json()["id"]
        self.decide(first, "reject")
        rows = self.api("GET", "/manage/challenge-proposals", as_user="root").json()
        self.assertEqual([(r["id"], r["status"]) for r in rows], [(second, "pending"), (first, "rejected")])
        waiting = self.api("GET", "/manage/challenge-proposals", as_user="root", params={"status": "pending"}).json()
        self.assertEqual([r["id"] for r in waiting], [second])

    def test_approving_launches_it_as_a_challenge_of_the_group(self):
        proposal = self.propose().json()["id"]
        response = self.decide(proposal, "approve")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["status"], body["decided_by"]), ("approved", "Root"))
        challenge = self.view(body["challenge_id"], "bea")
        self.assertEqual((challenge["scope"], challenge["title"], challenge["participation"]), ("group", "Juego del mes: Hades", "auto"))
        self.assertEqual(self.scalar("SELECT created_by FROM challenges"), self.root)
        mine = self.api("GET", "/challenges/proposals", as_user="ana").json()[0]
        self.assertEqual((mine["status"], mine["challenge_id"]), ("approved", challenge["id"]))

    def test_it_can_be_approved_as_a_voluntary_challenge(self):
        challenge_id = self.decide(self.propose().json()["id"], "approve", participation="opt_in").json()["challenge_id"]
        self.assertEqual(self.view(challenge_id)["participation"], "opt_in")

    def test_a_decided_proposal_cannot_be_decided_again(self):
        proposal = self.propose().json()["id"]
        self.assertEqual(self.decide(proposal, "approve").status_code, 200)
        for action in ("approve", "reject"):
            self.assertEqual(self.decide(proposal, action).status_code, 409, action)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 1)

    def test_one_that_cannot_be_launched_any_more_says_why_and_can_be_rejected(self):
        proposal = self.propose().json()["id"]
        with database.SessionLocal() as db:
            row = db.get(models.ChallengeProposal, proposal)
            row.options = json.dumps({**json.loads(row.options), "month": "2020-01"})
            db.commit()
        response = self.decide(proposal, "approve")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pasado", response.json()["detail"])
        self.assertEqual(self.scalar("SELECT status FROM challenge_proposals"), "pending")
        self.assertEqual(self.decide(proposal, "reject", note="Ya pasó el mes").status_code, 200)

    def test_a_rejection_keeps_the_note_for_the_proposer(self):
        proposal = self.propose().json()["id"]
        self.assertEqual(self.decide(proposal, "reject", note="  Mejor en noviembre  ").status_code, 200)
        mine = self.api("GET", "/challenges/proposals", as_user="ana").json()[0]
        self.assertEqual((mine["status"], mine["decision_note"], mine["decided_by"]), ("rejected", "Mejor en noviembre", "Root"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_only_an_admin_decides_and_an_unknown_proposal_is_a_404(self):
        proposal = self.propose().json()["id"]
        for action in ("approve", "reject"):
            self.assertEqual(self.decide(proposal, action, as_user="ana").status_code, 403, action)
        self.assertEqual(self.api("GET", "/manage/challenge-proposals", as_user="ana").status_code, 403)
        self.assertEqual(self.decide(9999, "approve").status_code, 404)

    def test_deleting_the_challenge_keeps_the_proposal_and_deleting_the_proposal_keeps_the_challenge(self):
        proposal = self.propose().json()["id"]
        challenge = self.decide(proposal, "approve").json()["challenge_id"]
        self.assertEqual(self.api("DELETE", f"/manage/challenges/{challenge}", as_user="root").status_code, 200)
        self.assertIsNone(self.scalar("SELECT challenge_id FROM challenge_proposals"))
        self.assertEqual(self.api("DELETE", f"/manage/challenge-proposals/{proposal}", as_user="root").status_code, 200)

    def test_the_decision_is_in_the_audit_log(self):
        proposal = self.propose().json()["id"]
        self.decide(proposal, "reject", note="no")
        rows = self.api("GET", "/manage/audit", as_user="root").json()
        rows = rows["items"] if isinstance(rows, dict) else rows
        self.assertTrue(any(r["entity"] == "challenge-proposals" and r["path"].endswith(f"/challenge-proposals/{proposal}/reject") for r in rows))


class ScheduleTestCase(AuthoringTestCase):
    def schedule(self, as_user="root", **changes):
        body = {"label": "Terror mensual", "kind": "themed", "theme": "Terror", "mode": "play", "min_hours_each": 2, **changes}
        return self.api("POST", "/manage/challenge-schedules", as_user=as_user, json=body)

    def rotation(self, **changes):
        body = {"label": "Juego del mes", "kind": "game_of_month", "games": ["hades", "celeste"], "min_hours_each": 3, "min_hours_total": 8, **changes}
        return self.api("POST", "/manage/challenge-schedules", as_user="root", json=body)

    def run(self, day):
        with database.SessionLocal() as db:
            return [(s.id, c.title) for s, c in challenge_schedules.run_due(db, day)]

    def titles(self):
        return [r[0] for r in self.rows("SELECT title FROM challenges ORDER BY starts_on, id")]


class ScheduleCreateTests(ScheduleTestCase):
    def test_it_starts_next_month_unless_it_is_asked_to_start_now(self):
        body = self.schedule().json()
        self.assertEqual((body["kind"], body["active"], body["announce"], body["participation"]), ("themed", True, False, "auto"))
        month = TODAY().replace(day=1)
        self.assertEqual(body["first_month"], challenges.next_month(month).isoformat())
        self.assertEqual(self.titles(), [])  # nothing launched now
        self.assertEqual(self.schedule(label="Otro", start_now=True).json()["first_month"], month.isoformat())

    def test_starting_now_launches_the_challenge_of_the_running_month_at_once(self):
        body = self.schedule(start_now=True).json()
        self.assertEqual(self.titles(), ["Temático: Horror"])
        self.assertEqual(body["last_month"], TODAY().replace(day=1).isoformat())
        self.assertIn("Lanzado: Temático: Horror", body["last_status"])
        challenge = self.api("GET", "/challenges", as_user="ana").json()[0]
        self.assertEqual((challenge["scope"], challenge["starts_on"]), ("group", TODAY().replace(day=1).isoformat()))
        self.assertEqual(self.scalar("SELECT created_by FROM challenges"), self.root)

    def test_what_cannot_be_launched_is_refused_when_it_is_defined(self):
        for changes, fragment in (
            ({"theme": "Nope"}, "temática"), ({"label": " "}, "nombre"), ({"label": "x" * 81}, "nombre"),
            ({"kind": "duel_hours"}, "programar"), ({"participation": "maybe"}, "voluntaria"), ({"mode": "win"}, "completar"),
        ):
            response = self.schedule(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        for games, fragment in (([], "al menos un juego"), (["nope"], "no existen"), (["hades"] * 3 + [f"g{n}" for n in range(30)], "como mucho")):
            response = self.rotation(games=games)
            self.assertEqual(response.status_code, 400, games)
            self.assertIn(fragment, response.json()["detail"], games)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenge_schedules"), 0)

    def test_only_an_admin_defines_schedules(self):
        self.assertEqual(self.schedule(as_user="ana").status_code, 403)
        self.assertEqual(self.api("GET", "/manage/challenge-schedules", as_user="ana").status_code, 403)

    def test_a_game_is_not_repeated_in_the_rotation(self):
        body = self.rotation(games=["hades", "celeste", "hades"]).json()
        self.assertEqual([g["id"] for g in body["games"]], ["hades", "celeste"])


class ScheduleRunTests(ScheduleTestCase):
    def month(self, offset):
        day = TODAY().replace(day=1)
        for _ in range(offset):
            day = challenges.next_month(day)
        return day

    def test_the_game_rotates_month_after_month_and_starts_over(self):
        self.rotation(start_now=True)
        self.assertEqual(self.titles(), ["Juego del mes: Hades"])
        self.assertEqual(self.run(self.month(1)), [(1, "Juego del mes: Celeste")])
        self.assertEqual(self.run(self.month(2)), [(1, "Juego del mes: Hades")])
        self.assertEqual(self.titles(), ["Juego del mes: Hades", "Juego del mes: Celeste", "Juego del mes: Hades"])

    def test_a_month_is_launched_once_however_many_times_it_runs(self):
        self.rotation(start_now=True)
        self.assertEqual(self.run(TODAY()), [])
        self.assertEqual(self.run(self.month(1) + timedelta(days=9)), [(1, "Juego del mes: Celeste")])  # a late run still launches it
        self.assertEqual(self.run(self.month(1) + timedelta(days=10)), [])
        self.assertEqual(len(self.titles()), 2)

    def test_it_does_not_launch_before_its_first_month_or_when_inactive(self):
        schedule = self.schedule().json()["id"]
        self.assertEqual(self.run(TODAY()), [])
        self.assertEqual(self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"active": False}).json()["active"], False)
        self.assertEqual(self.run(self.month(1)), [])
        self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"active": True})
        self.assertEqual(self.run(self.month(1)), [(schedule, "Temático: Horror")])

    def test_a_month_that_could_not_be_launched_says_why_and_is_not_tried_again(self):
        schedule = self.rotation(start_now=True).json()["id"]
        with database.SessionLocal() as db:
            db.query(models.ChallengeSchedule).update({"games": json.dumps(["ghost"])})
            db.commit()
        self.assertEqual(self.run(self.month(1)), [])
        status = self.api("GET", "/manage/challenge-schedules", as_user="root").json()[0]
        self.assertEqual(status["id"], schedule)
        self.assertIn("juego que exista", status["last_status"])
        self.assertEqual(status["last_month"], self.month(1).isoformat())
        self.assertEqual(self.run(self.month(1) + timedelta(days=1)), [])

    def test_an_equal_challenge_launched_by_hand_is_not_launched_twice(self):
        self.launch(game_id="hades", month=base.this_month(), min_hours_each=3, min_hours_total=8)
        body = self.rotation(start_now=True).json()
        self.assertEqual(self.titles(), ["Juego del mes: Hades"])
        self.assertIn("Ya existe un reto igual", body["last_status"])

    def test_a_voluntary_schedule_launches_voluntary_challenges(self):
        self.schedule(start_now=True, participation="opt_in")
        self.assertEqual(self.scalar("SELECT participation FROM challenges"), "opt_in")

    def test_without_its_admin_it_still_launches(self):
        self.schedule()
        with database.SessionLocal() as db:
            db.query(models.ChallengeSchedule).update({"created_by": None})
            db.commit()
        self.assertEqual(self.run(self.month(1)), [(1, "Temático: Horror")])
        self.assertIsNone(self.scalar("SELECT created_by FROM challenges"))

    def test_the_panel_names_the_game_of_this_month_and_the_next(self):
        self.rotation(start_now=True)
        body = self.api("GET", "/manage/challenge-schedules", as_user="root").json()[0]
        self.assertEqual((body["this_month"], body["next_month"], body["kind_label"]), ("Hades", "Celeste", "Juego del mes"))

    def test_changing_the_list_changes_the_rotation_and_the_options_stay(self):
        schedule = self.rotation(start_now=True).json()["id"]
        response = self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"games": ["tetris", "hades"], "label": "Nuevo nombre", "announce": True})
        body = response.json()
        self.assertEqual((body["label"], body["announce"], [g["id"] for g in body["games"]], body["next_month"]), ("Nuevo nombre", True, ["tetris", "hades"], "Hades"))
        self.assertEqual(body["options"], {"min_hours_each": 3.0, "min_hours_total": 8.0})
        self.assertEqual(self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"games": ["nope"]}).status_code, 400)

    def test_a_schedule_with_a_game_that_no_longer_exists_can_still_be_paused_and_renamed(self):
        schedule = self.rotation().json()["id"]
        with database.SessionLocal() as db:
            db.query(models.ChallengeSchedule).update({"games": json.dumps(["ghost", "celeste"])})
            db.commit()
        body = self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"active": False, "label": "En pausa"}).json()
        self.assertEqual((body["active"], body["label"]), (False, "En pausa"))
        again = self.api("PATCH", f"/manage/challenge-schedules/{schedule}", as_user="root", json={"participation": "opt_in"})
        self.assertEqual(again.status_code, 400)  # what decides the launch is still checked when it changes

    def test_deleting_a_schedule_keeps_what_it_launched(self):
        schedule = self.rotation(start_now=True).json()["id"]
        self.assertEqual(self.api("DELETE", f"/manage/challenge-schedules/{schedule}", as_user="root").status_code, 200)
        self.assertEqual(self.titles(), ["Juego del mes: Hades"])
        self.assertEqual(self.api("DELETE", f"/manage/challenge-schedules/{schedule}", as_user="root").status_code, 404)

    def test_the_rotation_follows_the_months_it_has_been_running(self):
        self.assertEqual(challenge_schedules.rotating_game(["a", "b", "c"], self.month(0), self.month(0)), "a")
        self.assertEqual(challenge_schedules.rotating_game(["a", "b", "c"], self.month(0), self.month(4)), "b")

    def test_a_year_end_is_crossed(self):
        december = clock.now().date().replace(month=12, day=1)
        self.assertEqual(challenge_schedules.rotating_game(["a", "b"], december, challenges.next_month(december)), "b")

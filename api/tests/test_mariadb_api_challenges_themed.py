"""The themed challenge, a group one launched from the admin panel (MariaDB required, see api_support.py): its options,
what counts for each mode, the optional total of the group and the notice when it is reached."""
import asyncio
from unittest import mock

from src.database import database
from src.utils import actions, my_utils
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY


class ThemedTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.game("amnesia", "Amnesia", tags="Horror, Singleplayer")
        self.game("alien", "Alien", tags="Atmospheric,Horror")
        self.game("tetris", "Tetris", tags="Puzzle")
        self.sent = []

        async def send(msg, silent, *args, **kwargs):
            self.sent.append(msg)

        patcher = mock.patch.object(my_utils, "send_message", new=send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def launch_themed(self, as_user="root", announce=False, **changes):
        body = {"kind": "themed", "tag": "Horror", "month": base.this_month(), "mode": "play", "min_hours_each": 2, "announce": announce, **changes}
        return self.api("POST", "/manage/challenges", as_user=as_user, json=body)

    def players(self, challenge_id, as_user="ana"):
        return {p["name"]: p for p in self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()["progress"]["players"]}

    def totals(self, challenge_id):
        return self.api("GET", f"/challenges/{challenge_id}", as_user="ana").json()["progress"]

    def announce_totals(self):
        with database.SessionLocal() as db:
            return asyncio.run(actions.announce_challenge_totals(db))


class LaunchTests(ThemedTestCase):
    def test_the_tags_to_choose_from_are_those_of_the_games_with_how_many_have_each(self):
        body = self.api("GET", "/manage/challenges/tags", as_user="root").json()
        self.assertEqual({t["tag"]: t["games"] for t in body}, {"Atmospheric": 1, "Horror": 2, "Puzzle": 1, "Singleplayer": 1})
        self.assertEqual(self.api("GET", "/manage/challenges/tags", as_user="ana").status_code, 403)

    def test_an_admin_launches_a_themed_challenge_for_the_group(self):
        response = self.launch_themed(tag="horror")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["game"]), ("themed", "group", "Temático: Horror", None))
        self.assertEqual(body["params"], {"tag": "Horror", "mode": "play", "min_hours_each": 2.0})  # the tag as the database writes it, no total
        self.assertEqual(sorted(body["progress"]["players"][0]), ["done", "name", "seconds", "target_seconds", "user_id"])
        self.assertNotIn("total_done", body["progress"])

    def test_a_player_cannot_and_the_challenges_route_never_makes_it(self):
        self.assertEqual(self.launch_themed(as_user="ana").status_code, 403)
        sent = {"kind": "themed", "options": {"tag": "Horror", "month": base.this_month(), "mode": "play", "min_hours_each": 2}}
        self.assertEqual(self.api("POST", "/challenges", as_user="root", json=sent).status_code, 403)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_the_options_are_checked(self):
        for changes, fragment in (
            ({"tag": "Nope"}, "temática"), ({"tag": ""}, "temática"), ({"mode": "win"}, "jugar o completar"),
            ({"month": "2026-13"}, "mes"), ({"min_hours_each": None}, "mínimo"), ({"min_hours_each": 0}, "mínimo"),
            ({"min_hours_total": 1}, "no puede ser menor"), ({"mode": "complete", "min_games_total": 0}, "juegos"),
            ({"mode": "complete", "min_games_total": 501}, "juegos"),
        ):
            response = self.launch_themed(**changes)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn(fragment, response.json()["detail"].lower(), changes)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_an_equal_challenge_is_refused_and_another_mode_or_total_is_not(self):
        self.assertEqual(self.launch_themed().status_code, 201)
        self.assertEqual(self.launch_themed().status_code, 409)
        self.assertEqual(self.launch_themed(min_hours_total=10).status_code, 201)
        self.assertEqual(self.launch_themed(mode="complete").status_code, 201)

    def test_a_completion_has_no_hours_and_the_group_is_told_only_if_asked(self):
        body = self.launch_themed(mode="complete", min_hours_each=None, announce=True).json()
        self.assertEqual(body["params"], {"tag": "Horror", "mode": "complete"})
        self.background["after_challenge_launch"].assert_called_once()


class PlayProgressTests(ThemedTestCase):
    def test_hours_in_every_game_with_the_tag_count_and_the_others_do_not(self):
        challenge = self.launch_themed().json()["id"]
        self.played(self.ana, 1.5, game="amnesia")
        self.played(self.ana, 1, game="alien")
        self.played(self.ana, 5, game="tetris")  # another tag
        self.played(self.bea, 1, game="amnesia")
        players = self.players(challenge)
        self.assertEqual((players["Ana"]["seconds"], players["Ana"]["done"]), (9000, True))
        self.assertEqual((players["Bea"]["seconds"], players["Bea"]["done"]), (3600, False))

    def test_the_tag_matches_a_whole_word_not_a_part_of_one(self):
        self.game("homerun", "Home Run", tags="Horror Comedy")  # one tag, with a space in it
        challenge = self.launch_themed().json()["id"]
        self.played(self.ana, 3, game="homerun")
        self.assertEqual(self.players(challenge)["Ana"]["seconds"], 0)

    def test_without_a_total_there_is_nothing_for_the_group_to_reach(self):
        challenge = self.launch_themed().json()["id"]
        self.played(self.ana, 9, game="amnesia")
        self.assertNotIn("total_done", self.totals(challenge))
        self.assertEqual(self.announce_totals(), 0)

    def test_with_a_total_the_group_hears_once_when_it_is_reached(self):
        self.launch_themed(min_hours_total=5)
        self.played(self.ana, 3, game="amnesia")
        self.assertEqual(self.announce_totals(), 0)
        self.played(self.bea, 2.5, game="alien")
        self.assertEqual(self.announce_totals(), 1)
        self.assertEqual(self.announce_totals(), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Reto cumplido", self.sent[0])
        self.assertIn("5 h de Horror", self.sent[0])
        self.assertIn("2 de 3 ya habéis cumplido", self.sent[0])


class CompleteProgressTests(ThemedTestCase):
    def completed(self, user, game):
        self.library_entry(user, game, TODAY(), "pc", completed=1, completed_date=TODAY())

    def test_completing_at_least_one_game_with_the_tag_in_the_period_is_what_each_player_does(self):
        challenge = self.launch_themed(mode="complete", min_hours_each=None).json()["id"]
        self.completed(self.ana, "amnesia")
        self.completed(self.ana, "alien")  # two count as one for her part
        self.completed(self.bea, "tetris")  # another tag
        players = self.players(challenge)
        self.assertEqual((players["Ana"]["count"], players["Ana"]["target_count"], players["Ana"]["done"]), (2, 1, True))
        self.assertEqual((players["Bea"]["count"], players["Bea"]["done"]), (0, False))

    def test_a_game_completed_before_the_period_does_not_count(self):
        challenge = self.launch_themed(mode="complete", min_hours_each=None).json()["id"]
        self.library_entry(self.ana, "amnesia", TODAY() - base.timedelta(days=90), "pc", completed=1, completed_date=TODAY() - base.timedelta(days=60))
        self.assertEqual(self.players(challenge)["Ana"]["count"], 0)

    def test_the_total_is_the_games_completed_between_everybody(self):
        challenge = self.launch_themed(mode="complete", min_hours_each=None, min_games_total=3).json()["id"]
        self.completed(self.ana, "amnesia")
        self.completed(self.bea, "alien")
        progress = self.totals(challenge)
        self.assertEqual((progress["total_count"], progress["total_target_count"], progress["total_done"]), (2, 3, False))
        self.assertEqual(self.announce_totals(), 0)
        self.completed(self.ana, "alien")
        self.assertEqual(self.announce_totals(), 1)
        self.assertIn("3 juegos completados de Horror", self.sent[0])


class OptOutTests(ThemedTestCase):
    def test_a_player_who_left_does_not_count_for_the_total(self):
        challenge = self.launch_themed(min_hours_total=4).json()["id"]
        self.played(self.ana, 3, game="amnesia")
        self.played(self.bea, 3, game="amnesia")
        self.api("PUT", f"/challenges/{challenge}/participation", as_user="bea", params={"joined": False})
        progress = self.totals(challenge)
        self.assertEqual((progress["total_seconds"], progress["total_done"]), (3 * 3600, False))

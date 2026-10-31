"""The themed challenge, a group one launched from the admin panel (MariaDB required, see api_support.py): its options,
what counts for each mode, the optional total of the group and the notice when it is reached."""
import asyncio
from datetime import timedelta
from unittest import mock

from src.database import database, models
from src.utils import actions, my_utils, themes
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY


class ThemedTestCase(base.ChallengesTestCase):
    def setUp(self):
        super().setUp()
        self.game("amnesia", "Amnesia", tags="Horror, Singleplayer")
        self.game("alien", "Alien", tags="Atmospheric,Horror")
        self.game("tetris", "Tetris", tags="Logic")
        self.sent = []

        async def send(msg, silent, *args, **kwargs):
            self.sent.append(msg)

        patcher = mock.patch.object(my_utils, "send_message", new=send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def launch_themed(self, as_user="root", announce=False, **changes):
        body = {"kind": "themed", "theme": "Terror", "month": base.this_month(), "mode": "play", "min_hours_each": 2, "announce": announce, **changes}
        return self.api("POST", "/manage/challenges", as_user=as_user, json=body)

    def players(self, challenge_id, as_user="ana"):
        return {p["name"]: p for p in self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()["progress"]["players"]}

    def totals(self, challenge_id):
        return self.api("GET", f"/challenges/{challenge_id}", as_user="ana").json()["progress"]

    def announce_totals(self):
        with database.SessionLocal() as db:
            return asyncio.run(actions.announce_challenge_totals(db))


class LaunchTests(ThemedTestCase):
    def test_the_themes_to_choose_from_are_those_with_games_the_one_with_most_first(self):
        body = self.api("GET", "/manage/challenges/themes", as_user="root").json()
        self.assertEqual(body, [{"theme": "Terror", "games": 2}, {"theme": "Puzles", "games": 1}])  # Atmospheric and Singleplayer are no theme
        self.assertEqual(self.api("GET", "/manage/challenges/themes", as_user="ana").status_code, 403)

    def test_a_game_counts_once_in_a_theme_however_many_of_its_tags_it_has(self):
        self.game("lights", "Lights", tags="Horror,Survival Horror,Spooky")
        body = self.api("GET", "/manage/challenges/themes", as_user="root").json()
        self.assertEqual(body[0], {"theme": "Terror", "games": 3})

    def test_an_admin_launches_a_themed_challenge_for_the_group(self):
        response = self.launch_themed(theme="terror")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["kind"], body["scope"], body["title"], body["game"]), ("themed", "group", "Temático: Terror", None))
        # the theme as the list writes it with the tags it had then, no total
        self.assertEqual(body["params"], {"theme": "Terror", "tags": list(themes.THEMES["Terror"]), "mode": "play", "min_hours_each": 2.0})
        self.assertEqual(sorted(body["progress"]["players"][0]), ["done", "name", "seconds", "target_seconds", "user_id"])
        self.assertNotIn("total_done", body["progress"])

    def test_a_challenge_made_with_a_single_tag_still_launches_and_counts(self):
        body = self.launch_themed(theme=None, tag="horror").json()
        self.assertEqual((body["title"], body["params"]), ("Temático: Horror", {"tag": "Horror", "mode": "play", "min_hours_each": 2.0}))
        self.played(self.ana, 2, game="alien")
        self.assertEqual(self.players(body["id"])["Ana"]["done"], True)

    def test_a_player_cannot_and_the_challenges_route_never_makes_it(self):
        self.assertEqual(self.launch_themed(as_user="ana").status_code, 403)
        sent = {"kind": "themed", "options": {"theme": "Terror", "month": base.this_month(), "mode": "play", "min_hours_each": 2}}
        self.assertEqual(self.api("POST", "/challenges", as_user="root", json=sent).status_code, 403)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM challenges"), 0)

    def test_the_options_are_checked(self):
        for changes, fragment in (
            ({"theme": "Nope"}, "temática"), ({"theme": ""}, "temática"), ({"theme": "Cyberpunk"}, "temática"), ({"mode": "win"}, "jugar o completar"),
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
        self.assertEqual(body["params"], {"theme": "Terror", "tags": list(themes.THEMES["Terror"]), "mode": "complete"})
        self.background["after_challenge_launch"].assert_called_once()


class GamesOfTheThemeTests(ThemedTestCase):
    def setUp(self):
        super().setUp()
        self.game("ghost", "Ghost", tags="Horror")  # nobody has it
        today = TODAY()
        self.library_entry(self.ana, "amnesia", today)
        self.library_entry(self.bea, "amnesia", today)
        self.library_entry(self.bea, "alien", today)
        self.library_entry(self.gone, "alien", today)  # an inactive player is not the group
        self.library_entry(self.ana, "tetris", today)  # another theme
        self.challenge = self.launch_themed().json()["id"]

    def games(self, as_user):
        return self.api("GET", f"/challenges/{self.challenge}/games", as_user=as_user).json()

    def test_the_games_of_the_theme_that_the_group_has_theirs_first_with_how_many_have_each(self):
        ana = [(g["name"], g["owners"], g["mine"]) for g in self.games("ana")]
        self.assertEqual(ana, [("Amnesia", 2, True), ("Alien", 1, False)])  # no Ghost (nobody has it), no Tetris (another theme)
        root = [(g["name"], g["mine"]) for g in self.games("root")]
        self.assertEqual(root, [("Amnesia", False), ("Alien", False)])  # the most owned first when none is theirs

    def test_the_challenge_says_how_many_games_the_group_has_and_how_many_the_viewer_has(self):
        summary = lambda user: self.api("GET", f"/challenges/{self.challenge}", as_user=user).json()["theme_games"]  # noqa: E731
        self.assertEqual((summary("ana"), summary("bea"), summary("root")), ({"available": 2, "mine": 1}, {"available": 2, "mine": 2}, {"available": 2, "mine": 0}))
        self.assertEqual(self.api("GET", "/challenges", as_user="ana").json()[0]["theme_games"], {"available": 2, "mine": 1})

    def test_only_a_themed_challenge_that_is_not_over_has_games(self):
        other = self.launch().json()
        self.assertIsNone(other["theme_games"])
        self.assertEqual(self.api("GET", f"/challenges/{other['id']}/games", as_user="ana").status_code, 400)
        self.assertEqual(self.api("GET", "/challenges/999/games", as_user="ana").status_code, 404)
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, self.challenge)
            row.starts_on, row.ends_on = TODAY() - timedelta(days=40), TODAY() - timedelta(days=2)
            db.commit()
        self.assertIsNone(self.api("GET", f"/challenges/{self.challenge}", as_user="ana").json()["theme_games"])


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

    def test_every_tag_of_the_theme_counts_but_a_game_is_not_counted_twice(self):
        self.game("lights", "Lights", tags="Horror,Survival Horror,Spooky")
        challenge = self.launch_themed().json()["id"]
        self.played(self.ana, 1, game="lights")  # three tags of the theme, one game
        self.played(self.ana, 1, game="alien")
        self.assertEqual(self.players(challenge)["Ana"]["seconds"], 7200)

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
        self.assertIn("5 h de Terror", self.sent[0])
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
        self.assertIn("3 juegos completados de Terror", self.sent[0])


class OptOutTests(ThemedTestCase):
    def test_a_player_who_left_does_not_count_for_the_total(self):
        challenge = self.launch_themed(min_hours_total=4).json()["id"]
        self.played(self.ana, 3, game="amnesia")
        self.played(self.bea, 3, game="amnesia")
        self.api("PUT", f"/challenges/{challenge}/participation", as_user="bea", params={"joined": False})
        progress = self.totals(challenge)
        self.assertEqual((progress["total_seconds"], progress["total_done"]), (3 * 3600, False))

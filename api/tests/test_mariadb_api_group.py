"""The group endpoints through real requests: the achievements and who has them (MariaDB required, see api_support.py)."""
import datetime
import unittest
from datetime import timedelta

from src.crud import group
from src.database import database, models
from tests.api_support import ApiTestCase

TODAY = datetime.date.today


class DescribeTests(unittest.TestCase):
    def test_the_markup_and_the_placeholders_become_a_sentence(self):
        self.assertEqual(
            group.describe("*{}* acaba de jugar 8 horas a _{}_ en un día."),
            "Alguien acaba de jugar 8 horas a un juego en un día.",
        )
        self.assertEqual(group.describe("{} lo logró {}"), "Alguien lo logró un juego")
        self.assertEqual(group.describe(None), "")


class AchievementsCatalogTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.gone = self.user("gone", active=False)
        self.game("celeste", "Celeste")
        ids = [row[0] for row in self.rows("SELECT id FROM achievements ORDER BY id LIMIT 2")]
        self.first, self.second = ids

    def award(self, user_id, achievement_id, day, game_id=None):
        with database.SessionLocal() as db:
            db.add(models.UserAchievement(user_id=user_id, achievement_id=achievement_id, date=day, game_id=game_id))
            db.commit()

    def catalog(self, as_user="ana"):
        return self.api("GET", "/group/achievements", as_user=as_user).json()

    def test_it_needs_a_login(self):
        self.assertEqual(self.api("GET", "/group/achievements").status_code, 401)

    def test_it_lists_every_achievement_but_hides_the_ones_the_viewer_lacks(self):
        self.award(self.bea, self.second, TODAY())
        self.award(self.ana, self.first, TODAY())
        body = self.catalog()
        self.assertEqual(len(body), self.scalar("SELECT COUNT(*) FROM achievements"))
        self.assertEqual([a["id"] for a in body], sorted(a["id"] for a in body))
        for achievement in body:
            if achievement["id"] == self.first:
                self.assertFalse(achievement["hidden"])
                self.assertNotIn("{}", achievement["description"])
                self.assertNotIn("*", achievement["description"])
            else:  # not even the name: the other player's unlock does not reveal it
                self.assertEqual(achievement, {"id": achievement["id"], "hidden": True, "unlocked_by_me": False})

    def test_who_has_it_how_many_times_and_when_last_the_latest_first(self):
        last = TODAY() - timedelta(days=400)
        self.award(self.ana, self.first, last)
        self.award(self.ana, self.first, TODAY() - timedelta(days=5))  # another season: it is earned once per season
        self.award(self.bea, self.first, TODAY() - timedelta(days=2))
        self.award(self.gone, self.first, TODAY())
        first = next(a for a in self.catalog() if a["id"] == self.first)
        self.assertEqual(first["unlocked_by"], 2)
        self.assertEqual([(p["name"], p["times"], p["last"]) for p in first["players"]],
                         [("Bea", 1, (TODAY() - timedelta(days=2)).isoformat()), ("Ana", 2, (TODAY() - timedelta(days=5)).isoformat())])

    def test_it_says_which_ones_are_yours(self):
        self.award(self.bea, self.second, TODAY())
        mine = {a["id"]: a["unlocked_by_me"] for a in self.catalog(as_user="ana")}
        theirs = {a["id"]: a["unlocked_by_me"] for a in self.catalog(as_user="bea")}
        self.assertFalse(mine[self.second])
        self.assertTrue(theirs[self.second])

    def test_the_page_of_another_player_hides_what_the_viewer_lacks(self):
        self.award(self.bea, self.first, TODAY())
        self.award(self.bea, self.second, TODAY())
        self.award(self.ana, self.first, TODAY())
        shown = self.api("GET", f"/group/players/{self.bea}", as_user="ana").json()["achievements"]
        self.assertEqual(sorted(a["hidden"] for a in shown), [False, True])
        self.assertTrue(all("title" not in a for a in shown if a["hidden"]))


class PlayersTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana", telegram_id=111)
        self.bea = self.user("bea")
        self.gone = self.user("gone", active=False)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")

    def players(self, as_user="ana"):
        return self.api("GET", "/group/players", as_user=as_user).json()

    def test_they_need_a_login(self):
        self.assertEqual(self.api("GET", "/group/players").status_code, 401)
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}").status_code, 401)

    def test_only_the_active_players_with_their_figures(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=5), 60)
        self.session(self.ana, "hades", datetime.datetime.now() - timedelta(hours=3), 30)
        self.library_entry(self.gone, "celeste", TODAY(), "pc")
        rows = {p["name"]: p for p in self.players()}
        self.assertEqual(sorted(rows), ["Ana", "Bea"])
        self.assertEqual((rows["Ana"]["played_seconds"], rows["Ana"]["games"], rows["Ana"]["completed"], rows["Ana"]["achievements"]), (5400, 2, 1, 0))
        self.assertEqual((rows["Bea"]["games"], rows["Bea"]["last_played"], rows["Bea"]["playing"]), (0, None, None))
        self.assertEqual((rows["Ana"]["is_me"], rows["Bea"]["is_me"]), (True, False))

    def test_the_ones_playing_come_first_then_the_latest_to_play(self):
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=2), 30)
        self.session(self.bea, "hades", datetime.datetime.now() - timedelta(hours=9), 30)
        cai = self.user("cai")
        self.api("POST", "/timers/start", as_user="cai", json={"user_id": cai, "game_id": "celeste", "platform": "pc"})
        body = self.players()
        self.assertEqual([p["name"] for p in body], ["Cai", "Ana", "Bea"])
        self.assertEqual(body[0]["playing"]["game_name"], "Celeste")

    def test_hiding_removes_only_the_live_status(self):
        self.api("POST", "/timers/start", as_user="bea", json={"user_id": self.bea, "game_id": "hades", "platform": "pc"})
        self.api("PATCH", "/users/bea/settings", as_user="bea", json={"show_playing": False})
        bea = next(p for p in self.players(as_user="ana") if p["name"] == "Bea")
        self.assertIsNone(bea["playing"])  # but she is still listed
        self.assertIsNotNone(next(p for p in self.players(as_user="bea") if p["name"] == "Bea")["playing"])

    def test_the_page_of_a_player_has_what_is_public_and_nothing_private(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=3), 90)
        with database.SessionLocal() as db:
            db.add(models.GameScore(user_id=self.ana, game_id="celeste", score=77))
            db.commit()
        body = self.api("GET", f"/group/players/{self.ana}", as_user="bea").json()
        self.assertEqual(body["user"], {"id": self.ana, "username": "ana", "name": "Ana"})
        self.assertEqual(body["stats"]["played_time"], 5400)
        self.assertEqual([(g["game_name"], g["score"]) for g in body["top_games"]], [("Celeste", 77)])
        self.assertEqual(body["is_me"], False)
        self.assertEqual(set(body), {"user", "season", "seasons", "stats", "top_games", "achievements", "playing", "is_me"})
        self.assertNotIn("111", str(body))  # the Telegram id
        self.assertNotIn("example.com", str(body))  # the email

    def test_a_season_or_all_of_them_and_the_limits_of_the_parameter(self):
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=3), 60)
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "all"}).json()["season"], "all")
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "2020"}).json()["season"], 2020)
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "x"}).status_code, 422)

    def test_unknown_and_inactive_players_are_not_found(self):
        self.assertEqual(self.api("GET", "/group/players/999999", as_user="ana").status_code, 404)
        self.assertEqual(self.api("GET", f"/group/players/{self.gone}", as_user="ana").status_code, 404)

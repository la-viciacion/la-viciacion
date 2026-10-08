"""The group endpoints through real requests: the achievements and who has them (MariaDB required, see api_support.py)."""
import datetime
import unittest
from datetime import timedelta

from sqlalchemy import text

from src.crud import group
from src.database import database, models
from tests.api_support import ApiTestCase
from tests import clock

TODAY = clock.today


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
        with self.engine.begin() as conn:  # some are secret or special in the catalogue: each test says what it needs
            conn.execute(text("UPDATE achievements SET secret = 0, special = 0"))
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

    def test_it_lists_every_achievement_and_the_ones_the_viewer_lacks_come_in_full_for_the_front_to_dim(self):
        self.award(self.bea, self.second, TODAY())
        self.award(self.ana, self.first, TODAY())
        body = self.catalog()
        with self.engine.begin() as conn:
            upcoming = {row[0] for row in conn.execute(text("SELECT id FROM achievements WHERE valid_from_season > :y"), {"y": TODAY().year})}
        self.assertEqual(len(body), self.scalar("SELECT COUNT(*) FROM achievements WHERE valid_from_season <= :y OR active = 1", y=TODAY().year))  # the ones of a later season are there too, hidden
        self.assertEqual([a["id"] for a in body], sorted(a["id"] for a in body))
        for achievement in body:
            if achievement["id"] == self.first:
                self.assertFalse(achievement["hidden"])
                self.assertNotIn("{}", achievement["description"])
                self.assertNotIn("*", achievement["description"])
            else:  # it is there to aim for: nothing is secret, but the ones of a later season are still hidden
                self.assertEqual(achievement["hidden"], achievement["id"] in upcoming)
                self.assertFalse(achievement["unlocked_by_me"])
                if achievement["hidden"]:
                    self.assertEqual(set(achievement), {"id", "hidden", "unlocked_by_me", "secret", "special", "lifetime", "unlocked_by", "players"})  # no name, only who has it
                    continue
                self.assertTrue(achievement["title"])
                self.assertIsNone(achievement["description"])  # what it is about is for whoever earns it
                self.assertIsNone(achievement["key"])  # nor its key, nor its picture: they would say it
                self.assertFalse(achievement["has_image"])
        self.assertEqual([p["name"] for p in next(a for a in body if a["id"] == self.second)["players"]], ["Bea"])

    def test_a_secret_one_is_hidden_from_whoever_lacks_it_and_nothing_else_about_it_is_known(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET secret = 1 WHERE id IN (:a, :b)"), {"a": self.first, "b": self.second})
        self.award(self.ana, self.first, TODAY())
        by_id = {a["id"]: a for a in self.catalog()}
        self.assertTrue(by_id[self.first]["secret"])
        # whoever lacks it knows that it exists, and nothing more
        self.assertEqual(by_id[self.second], {"id": self.second, "hidden": True, "unlocked_by_me": False, "secret": True, "special": 0, "lifetime": False,
                                              "unlocked_by": 0, "players": []})

    def test_a_hidden_one_says_who_has_it_and_nothing_else_so_that_it_is_seen_to_be_possible(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET secret = 1 WHERE id = :a"), {"a": self.second})
        self.award(self.bea, self.second, TODAY())
        self.award(self.gone, self.second, TODAY() - datetime.timedelta(days=1))
        seen = {a["id"]: a for a in self.catalog("ana")}[self.second]
        self.assertTrue(seen["hidden"])
        self.assertEqual(seen["unlocked_by"], 2)
        self.assertEqual(seen["players"], [{"user_id": self.bea, "name": "Bea"}, {"user_id": self.gone, "name": "Gone"}])  # the latest first, no date
        for key in ("title", "description", "key", "has_image", "progress"):
            self.assertNotIn(key, seen)
        self.assertTrue({a["id"]: a for a in self.catalog("bea")}[self.second]["unlocked_by_me"])  # whoever has it sees it in full

    def test_the_level_of_a_special_one_is_known_to_everybody_even_when_it_is_locked_and_a_special_one_is_always_hidden(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET special = 3, secret = 1 WHERE id = :a"), {"a": self.first})
            conn.execute(text("UPDATE achievements SET special = 1 WHERE id = :a"), {"a": self.second})
        by_id = {a["id"]: a for a in self.catalog()}
        self.assertEqual(by_id[self.first], {"id": self.first, "hidden": True, "unlocked_by_me": False, "secret": True, "special": 3, "lifetime": False,
                                             "unlocked_by": 0, "players": []})  # the lock and its aura
        self.assertEqual((by_id[self.second]["hidden"], by_id[self.second]["special"], by_id[self.second]["secret"]), (True, 1, True))  # special: hidden even if not marked
        self.award(self.ana, self.first, TODAY())
        self.assertEqual({a["id"]: a["special"] for a in self.catalog()}[self.first], 3)

    def test_the_ones_with_no_season_limit_say_so_once_unlocked(self):
        lifetime = self.scalar("SELECT id FROM achievements WHERE `key` = 'PLAYED_100_DAYS_LIFETIME'")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET valid_from_season = 2023 WHERE id = :id"), {"id": lifetime})  # valid, so the others see it as a hidden one
        self.award(self.ana, lifetime, TODAY())
        by_id = {a["id"]: a for a in self.catalog()}
        self.assertTrue(by_id[lifetime]["lifetime"])
        other = self.catalog("bea")
        seen = next(a for a in other if a["id"] == lifetime)  # whoever lacks it sees it, once, dimmed
        self.assertEqual((seen["hidden"], seen["unlocked_by_me"], seen["lifetime"]), (False, False, True))

    def test_one_that_is_not_valid_yet_is_listed_hidden_unless_the_viewer_has_it(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET valid_from_season = :s WHERE id IN (:a, :b)"), {"s": TODAY().year + 1, "a": self.first, "b": self.second})
        self.award(self.ana, self.first, TODAY())
        by_id = {a["id"]: a for a in self.catalog()}
        self.assertFalse(by_id[self.first]["hidden"])  # she has it: it shows in full
        self.assertEqual(by_id[self.second], {"id": self.second, "hidden": True, "unlocked_by_me": False, "secret": False, "special": 0, "lifetime": False,
                                              "unlocked_by": 0, "players": []})

    def test_one_that_is_not_valid_yet_keeps_its_aura_and_is_not_there_in_a_closed_season(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET special = 2, valid_from_season = :s WHERE id = :a"), {"s": TODAY().year + 1, "a": self.second})
        by_id = {a["id"]: a for a in self.catalog("bea")}
        self.assertEqual((by_id[self.second]["hidden"], by_id[self.second]["special"]), (True, 2))
        self.assertNotIn(self.second, {a["id"] for a in self.api("GET", f"/group/achievements?season={TODAY().year - 1}", as_user="bea").json()})  # not in a closed season
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET active = 0 WHERE id = :a"), {"a": self.second})
        self.assertNotIn(self.second, {a["id"] for a in self.catalog("bea")})  # switched off: it does not exist

    def test_a_switched_off_achievement_does_not_exist_for_the_group_unless_the_viewer_has_it(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET active = 0 WHERE id IN (:a, :b)"), {"a": self.first, "b": self.second})
        self.award(self.ana, self.first, TODAY())
        shown = {a["id"] for a in self.catalog()}
        self.assertIn(self.first, shown)  # she has it
        self.assertNotIn(self.second, shown)  # nobody can have it: not even as a hidden one
        self.assertEqual(len(self.catalog("ana")), self.scalar("SELECT COUNT(*) FROM achievements WHERE active = 1", y=TODAY().year) + 1)

    def test_who_has_it_in_the_season_and_when_last_the_latest_first(self):
        year = TODAY().year
        self.award(self.ana, self.first, datetime.date(year - 1, 5, 1))  # earned once per season: another season's is not counted
        self.award(self.ana, self.first, datetime.date(year, 1, 5))
        self.award(self.bea, self.first, datetime.date(year, 1, 20))
        self.award(self.gone, self.first, datetime.date(year, 2, 1))  # a player who no longer plays still earned it
        first = next(a for a in self.catalog() if a["id"] == self.first)
        self.assertEqual(first["unlocked_by"], 3)
        self.assertEqual([(p["name"], p["times"], p["last"]) for p in first["players"]],
                         [("Gone", 1, f"{year}-02-01"), ("Bea", 1, f"{year}-01-20"), ("Ana", 1, f"{year}-01-05")])

    def test_a_past_season_shows_what_that_season_had(self):
        year = TODAY().year
        self.award(self.ana, self.first, datetime.date(year - 1, 5, 1))
        self.award(self.bea, self.first, datetime.date(year, 1, 20))
        past = self.api("GET", "/group/achievements", as_user="ana", params={"season": year - 1}).json()
        first = next(a for a in past if a["id"] == self.first)
        self.assertEqual((first["unlocked_by"], first["unlocked_by_me"], first["players"][0]["name"]), (1, True, "Ana"))
        now = next(a for a in self.catalog() if a["id"] == self.first)
        self.assertEqual((now["unlocked_by"], now["unlocked_by_me"], now["players"][0]["name"]), (1, False, "Bea"))
        self.assertIsNotNone(now["description"])  # ana knows what it is: she earned it once

    def test_a_season_that_has_not_started_is_refused(self):
        self.assertEqual(self.api("GET", "/group/achievements", as_user="ana", params={"season": TODAY().year + 1}).status_code, 400)
        self.assertEqual(self.api("GET", "/group/achievements", as_user="ana", params={"season": "x"}).status_code, 422)

    def test_the_emergency_account_never_counts(self):
        god = self.user("admin", admin=True)  # the emergency account
        self.award(god, self.first, TODAY())
        first = next(a for a in self.catalog() if a["id"] == self.first)
        self.assertEqual(first["unlocked_by"], 0)

    def test_it_says_which_ones_are_yours(self):
        self.award(self.bea, self.second, TODAY())
        mine = {a["id"]: a["unlocked_by_me"] for a in self.catalog(as_user="ana")}
        theirs = {a["id"]: a["unlocked_by_me"] for a in self.catalog(as_user="bea")}
        self.assertFalse(mine[self.second])
        self.assertTrue(theirs[self.second])

    def test_the_page_of_another_player_hides_the_secret_ones_the_viewer_lacks(self):
        self.award(self.bea, self.first, TODAY())
        self.award(self.bea, self.second, TODAY())
        self.award(self.ana, self.first, TODAY())
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET secret = 1, special = 2 WHERE id = :a"), {"a": self.second})
        shown = self.api("GET", f"/group/players/{self.bea}", as_user="ana").json()["achievements"]
        self.assertEqual(sorted(a["hidden"] for a in shown), [False, True])
        self.assertTrue(all("title" not in a for a in shown if a["hidden"]))
        self.assertEqual([a["special"] for a in shown if a["hidden"]], [2])  # its aura is public
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET secret = 0 WHERE id = :a"), {"a": self.second})
        shown = self.api("GET", f"/group/players/{self.bea}", as_user="ana").json()["achievements"]
        self.assertEqual(sorted(a["hidden"] for a in shown), [False, True])  # still special: as hidden as a secret one
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET special = 0 WHERE id = :a"), {"a": self.second})
        shown = self.api("GET", f"/group/players/{self.bea}", as_user="ana").json()["achievements"]
        self.assertEqual([a["hidden"] for a in shown], [False, False])  # nothing is hidden when nothing is secret or special


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

    def test_every_player_with_their_figures_and_whether_they_are_active(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=5), 60)
        self.session(self.ana, "hades", datetime.datetime.now() - timedelta(hours=3), 30)
        self.library_entry(self.gone, "celeste", TODAY(), "pc")
        rows = {p["name"]: p for p in self.players()}
        self.assertEqual(sorted(rows), ["Ana", "Bea", "Gone"])
        self.assertEqual((rows["Ana"]["is_active"], rows["Gone"]["is_active"], rows["Gone"]["games"]), (True, False, 1))
        self.assertEqual((rows["Ana"]["played_seconds"], rows["Ana"]["games"], rows["Ana"]["completed"], rows["Ana"]["achievements"]), (5400, 2, 1, 0))
        self.assertEqual((rows["Bea"]["games"], rows["Bea"]["last_played"], rows["Bea"]["playing"]), (0, None, None))
        self.assertEqual((rows["Ana"]["is_me"], rows["Bea"]["is_me"]), (True, False))

    def test_the_ones_playing_come_first_then_the_latest_to_play(self):
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=2), 30)
        self.session(self.bea, "hades", datetime.datetime.now() - timedelta(hours=9), 30)
        cai = self.user("cai")
        self.api("POST", "/timers/start", as_user="cai", json={"user_id": cai, "game_id": "celeste", "platform": "pc"})
        body = self.players()
        self.assertEqual([p["name"] for p in body], ["Cai", "Ana", "Bea", "Gone"])
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
        self.assertEqual(set(body), {"user", "season", "seasons", "stats", "top_games", "achievements", "playing", "is_active", "is_me"})
        self.assertNotIn("111", str(body))  # the Telegram id
        self.assertNotIn("example.com", str(body))  # the email

    def test_a_season_or_all_of_them_and_the_limits_of_the_parameter(self):
        self.session(self.ana, "celeste", datetime.datetime.now() - timedelta(hours=3), 60)
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "all"}).json()["season"], "all")
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "2020"}).json()["season"], 2020)
        self.assertEqual(self.api("GET", f"/group/players/{self.ana}", as_user="bea", params={"season": "x"}).status_code, 422)

    def test_an_inactive_player_has_a_page_and_an_unknown_one_does_not(self):
        self.assertEqual(self.api("GET", "/group/players/999999", as_user="ana").status_code, 404)
        gone = self.api("GET", f"/group/players/{self.gone}", as_user="ana")
        self.assertEqual((gone.status_code, gone.json()["is_active"]), (200, False))

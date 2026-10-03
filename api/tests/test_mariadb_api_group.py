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

    def test_it_lists_every_achievement_even_the_ones_nobody_has(self):
        body = self.catalog()
        self.assertEqual(len(body), self.scalar("SELECT COUNT(*) FROM achievements"))
        self.assertEqual([a["id"] for a in body], sorted(a["id"] for a in body))
        first = next(a for a in body if a["id"] == self.first)
        self.assertEqual((first["unlocked_by"], first["unlocked_by_me"], first["players"], first["has_image"]), (0, False, [], False))
        for achievement in body:
            self.assertNotIn("{}", achievement["description"])
            self.assertNotIn("*", achievement["description"])

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

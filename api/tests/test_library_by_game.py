import datetime
import unittest

from src.crud import users
from src.database import models
from tests.sqlite_db import make_session


class LibraryByGameTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        today = datetime.date.today()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.Game(id="doom", name="Doom"),
            models.Game(id="hades", name="Hades"),
            models.PlatformTag(id="pc", name="PC"),
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=today, completed=0),
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=today.replace(year=today.year - 1), completed=1),
            models.UserGame(user_id=1, game_id="hades", platform="pc", started_date=today, completed=0),
        ])
        self.db.commit()

    def test_without_a_game_every_entry_is_listed(self):
        self.assertEqual(users.get_library(self.db, 1)["total"], 3)

    def test_with_a_game_only_its_entries_are_listed_and_counted(self):
        got = users.get_library(self.db, 1, game_id="doom")
        self.assertEqual(got["total"], 2)
        self.assertEqual({i["game_id"] for i in got["items"]}, {"doom"})


class LibraryGroupsPlatformsTests(unittest.TestCase):
    """A game played on several platforms in a season is one row, standing for all of its entries."""

    def setUp(self):
        self.db = make_session()
        self.day = datetime.date(2026, 10, 10)
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.Game(id="ac", name="Animal Crossing"),
            models.PlatformTag(id="switch", name="Nintendo Switch"),
            models.PlatformTag(id="switch2", name="Nintendo Switch 2"),
            models.UserGame(id=1, user_id=1, game_id="ac", platform="switch", started_date=self.day, completed=0),
            models.UserGame(id=2, user_id=1, game_id="ac", platform="switch2", started_date=self.day, completed=0),
            models.UserGame(id=3, user_id=1, game_id="ac", platform="switch", started_date=self.day.replace(year=2025), completed=0),
        ])
        self.db.commit()

    def library(self):
        return users.get_library(self.db, 1)

    def test_the_platforms_of_a_season_are_one_row_and_one_in_the_count(self):
        got = self.library()
        self.assertEqual(got["total"], 2)
        self.assertEqual([(i["season"], i["id"]) for i in got["items"]], [(2026, 2), (2025, 3)])

    def test_the_row_lists_every_platform_of_its_season_most_recent_first(self):
        item = self.library()["items"][0]
        self.assertEqual([p["id"] for p in item["platforms"]], ["switch2", "switch"])
        self.assertEqual([p["id"] for p in self.library()["items"][1]["platforms"]], ["switch"])

    def test_a_completed_entry_stands_for_the_group(self):
        self.db.get(models.UserGame, 1).completed = 1
        self.db.commit()
        item = self.library()["items"][0]
        self.assertEqual((item["id"], item["completed"]), (1, True))

    def test_an_entry_asked_by_id_is_returned_even_when_it_is_not_the_one_on_the_list(self):
        item = users.get_library_item(self.db, 1, 1)
        self.assertEqual(item["id"], 1)
        self.assertEqual([p["id"] for p in item["platforms"]], ["switch2", "switch"])

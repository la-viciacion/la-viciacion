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

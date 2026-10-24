import datetime

from sqlalchemy import text

from src.crud import users
from src.database import models
from tests.mariadb_db import MariaDBTestCase


class LibraryPlatformsTests(MariaDBTestCase):
    """The platforms of a library row, on a real MariaDB: the generated `season` column cannot be trusted in a
    query that is answered from the unique index and sorted (MariaDB 12 gives 0), and SQLite does not show it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        models.Base.metadata.create_all(cls.engine)

    def setUp(self):
        self.db = self.session()
        self.addCleanup(self.db.close)
        with self.engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in ("users_games", "platform_tags", "games", "users"):
                conn.execute(text(f"DELETE FROM `{table}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        day = datetime.date(2026, 10, 10)
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.Game(id="gt", name="Gran Turismo"),
            models.PlatformTag(id="ps5", name="PlayStation 5"),
            models.PlatformTag(id="ps4", name="PlayStation 4"),
            models.UserGame(id=1, user_id=1, game_id="gt", platform="ps5", started_date=day, completed=0),
            models.UserGame(id=2, user_id=1, game_id="gt", platform="ps5", started_date=day.replace(year=2025), completed=1),
            models.UserGame(id=3, user_id=1, game_id="gt", platform="ps4", started_date=day.replace(year=2025), completed=0),
        ])
        # the bug needs the planner to answer from the unique index, which it only does with a table of some size
        self.db.add_all([models.Game(id=f"pad{n}", name=f"Pad {n}") for n in range(60)])
        self.db.flush()
        self.db.add_all([
            models.UserGame(user_id=1, game_id=f"pad{n}", platform="ps5", started_date=day.replace(year=2023 + year), completed=0)
            for n in range(60) for year in range(4)
        ])
        self.db.commit()
        with self.engine.begin() as conn:
            conn.execute(text("ANALYZE TABLE users_games"))

    def test_every_row_names_the_platforms_of_its_own_season(self):
        items = {i["season"]: i for i in users.get_library(self.db, 1, game_id="gt")["items"]}
        self.assertEqual([p["id"] for p in items[2026]["platforms"]], ["ps5"])
        self.assertEqual({p["id"] for p in items[2025]["platforms"]}, {"ps5", "ps4"})

    def test_the_platforms_of_one_game_and_of_all_of_them_agree(self):
        alone = {i["season"]: i["platforms"] for i in users.get_library(self.db, 1, game_id="gt")["items"]}
        every = [i for offset in range(0, 300, 100) for i in users.get_library(self.db, 1, limit=100, offset=offset)["items"]]
        self.assertEqual(len(every), users.get_library(self.db, 1)["total"])
        self.assertEqual({i["season"]: i["platforms"] for i in every if i["game_id"] == "gt"}, alone)
        self.assertTrue(all(i["platforms"] for i in every))

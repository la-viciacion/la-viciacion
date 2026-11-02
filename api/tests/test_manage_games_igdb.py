"""What the admin can read and change of the IGDB data of a game from the panel."""
import unittest

from src.database import models
from src.routers.manage import games as manage_games
from tests.sqlite_db import make_session


class IgdbFieldsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hades II", igdb_id=228525))
        self.db.commit()

    def test_the_page_and_the_data_of_igdb_can_be_corrected_by_hand(self):
        out = manage_games.patch_game("g", manage_games.GamePatch(igdb_slug="hades-ii", themes="Fantasy", franchises="Hades", collections="Hades"), self.db)
        self.assertEqual((out["igdb_id"], out["igdb_slug"], out["themes"], out["franchises"], out["collections"]), (228525, "hades-ii", "Fantasy", "Hades", "Hades"))
        self.assertEqual(self.db.get(models.Game, "g").links, [{"name": "IGDB", "url": "https://www.igdb.com/games/hades-ii"}])

    def test_an_address_that_is_not_a_slug_is_kept_but_never_becomes_a_link(self):
        manage_games.patch_game("g", manage_games.GamePatch(igdb_slug="x) [evil](http://evil.example"), self.db)
        self.assertEqual(self.db.get(models.Game, "g").links, [])


if __name__ == "__main__":
    unittest.main()

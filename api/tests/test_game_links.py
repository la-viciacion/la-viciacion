"""Where a game's page is: a slug belongs to the site it came from, and what reads a notice's links knows both sites."""
import unittest

from src.database import models
from src.utils import inbox, my_utils


class PageUrlTests(unittest.TestCase):
    def test_a_game_with_a_rawg_id_or_no_id_links_to_rawg(self):
        self.assertEqual(models.Game(slug="hades", rawg_id=1).page_url, "https://rawg.io/games/hades")
        self.assertEqual(models.Game(slug="hades", rawg_id=1, igdb_id=2).page_url, "https://rawg.io/games/hades")
        self.assertEqual(models.Game(slug="hades").page_url, "https://rawg.io/games/hades")  # from before IGDB

    def test_a_game_only_igdb_knows_links_to_igdb(self):
        self.assertEqual(models.Game(slug="hades-ii", igdb_id=2).page_url, "https://www.igdb.com/games/hades-ii")

    def test_without_a_slug_there_is_no_page(self):
        self.assertIsNone(models.Game(igdb_id=2).page_url)
        self.assertIsNone(models.Game(slug="", rawg_id=1).page_url)


class LinkTests(unittest.TestCase):
    def test_a_notice_links_a_url_as_it_is_and_a_bare_slug_to_rawg(self):
        self.assertEqual(my_utils.rawg_game_link("Hades II", "https://www.igdb.com/games/hades-ii"), "[Hades II](https://www.igdb.com/games/hades-ii)")
        self.assertEqual(my_utils.rawg_game_link("Hades", "hades"), "[Hades](https://rawg.io/games/hades)")
        self.assertEqual(my_utils.rawg_game_link("Hades", None), "Hades")

    def test_the_inbox_keeps_the_links_of_both_sites(self):
        message = "Hoy sale [Hades II](https://www.igdb.com/games/hades-ii) y [Celeste](https://rawg.io/games/celeste)"
        body = inbox.linked_body(message, "Hoy sale Hades II y Celeste")
        self.assertEqual(body, message)


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(models.Game(igdb_slug="hades-ii", igdb_id=2).page_url, "https://www.igdb.com/games/hades-ii")
        self.assertEqual(models.Game(slug="hades-ii", igdb_id=2).page_url, "https://www.igdb.com/games/hades-ii")  # before igdb_slug

    def test_without_a_slug_there_is_no_page(self):
        self.assertIsNone(models.Game(igdb_id=2).page_url)
        self.assertIsNone(models.Game(slug="", rawg_id=1).page_url)


class LinksTests(unittest.TestCase):
    def test_a_game_has_the_page_of_the_source_its_slug_belongs_to(self):
        self.assertEqual(models.Game(slug="hades", rawg_id=1).links, [{"name": "RAWG", "url": "https://rawg.io/games/hades"}])
        self.assertEqual(models.Game(slug="hades-ii", igdb_id=2).links, [{"name": "IGDB", "url": "https://www.igdb.com/games/hades-ii"}])  # created by IGDB before igdb_slug
        self.assertEqual(models.Game(igdb_id=2).links, [])

    def test_a_game_with_both_ids_links_to_igdb_first_and_rawg_after(self):
        game = models.Game(slug="hades", igdb_slug="hades--1", rawg_id=1, igdb_id=2)
        self.assertEqual(game.links, [{"name": "IGDB", "url": "https://www.igdb.com/games/hades--1"}, {"name": "RAWG", "url": "https://rawg.io/games/hades"}])
        self.assertEqual(game.page_url, "https://www.igdb.com/games/hades--1")  # what the notices link to

    def test_until_igdbs_address_is_known_the_notices_keep_rawgs(self):
        game = models.Game(slug="hades", rawg_id=1, igdb_id=2)
        self.assertEqual(game.page_url, "https://rawg.io/games/hades")
        self.assertEqual([link["name"] for link in game.links], ["RAWG"])

    def test_a_game_without_a_rawg_id_has_no_rawg_page_even_with_a_slug(self):
        self.assertEqual([link["name"] for link in models.Game(slug="x", igdb_slug="y", igdb_id=2).links], ["IGDB"])


class UnsafeSlugTests(unittest.TestCase):
    def test_a_slug_that_is_not_what_the_sites_use_never_becomes_a_link(self):
        for slug in ("x) [evil](http://evil.example", "has space", "../../etc", "", "-leading", "a/b"):
            self.assertEqual(models.Game(slug=slug, rawg_id=1).links, [], slug)
            self.assertEqual(models.Game(igdb_slug=slug, igdb_id=2).links, [], slug)
            self.assertIsNone(models.Game(slug=slug, rawg_id=1).page_url)

    def test_the_slugs_the_sites_really_use_are_links(self):
        for slug in ("hades--1", "the-legend-of-zelda-tears-of-the-kingdom", "diablo-iv", "game_2.0", "a"):
            self.assertEqual(len(models.Game(slug=slug, rawg_id=1).links), 1, slug)


class LinkTests(unittest.TestCase):
    def test_a_notice_links_a_url_as_it_is_and_a_bare_slug_to_rawg(self):
        self.assertEqual(my_utils.game_link("Hades II", "https://www.igdb.com/games/hades-ii"), "[Hades II](https://www.igdb.com/games/hades-ii)")
        self.assertEqual(my_utils.game_link("Hades", "hades"), "[Hades](https://rawg.io/games/hades)")
        self.assertEqual(my_utils.game_link("Hades", None), "Hades")

    def test_the_inbox_keeps_the_links_of_both_sites(self):
        message = "Hoy sale [Hades II](https://www.igdb.com/games/hades-ii) y [Celeste](https://rawg.io/games/celeste)"
        body = inbox.linked_body(message, "Hoy sale Hades II y Celeste")
        self.assertEqual(body, message)


if __name__ == "__main__":
    unittest.main()

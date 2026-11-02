import datetime
import unittest
from unittest import mock

from fastapi import HTTPException

from src.clients import igdb
from src.database import models
from src.routers.manage import games
from src.utils import hltb_sync, igdb_sync, rawg_sync
from tests.sqlite_db import make_session

DETAILS = {
    "rawg_id": 391403, "slug": "path-of-exile-2", "dev": "Grinding Gear Games",
    "release_date": datetime.date(2026, 12, 11), "image_url": "https://img/poe2.jpg",
    "genres": "Action,RPG", "tags": "", "steam_id": "2694490",
}


def entry(name, seconds, game_id=1, year=2026, kind="game"):
    return mock.Mock(game_id=game_id, game_name=name, game_alias="", game_type=kind, release_world=year, json_content={"comp_main": seconds})


class RawgResyncTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Path of Exile 2", release_date=datetime.date(2026, 6, 1), image_url="old"))
        self.db.commit()
        for patcher in (
            mock.patch.object(type(rawg_sync.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="k"),
            mock.patch.object(rawg_sync, "_details", return_value=dict(DETAILS)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def game(self):
        return self.db.get(models.Game, "g")

    def test_a_linked_game_overwrites_what_rawg_gives_without_searching(self):
        self.game().rawg_id = 391403
        self.db.commit()
        with mock.patch.object(rawg_sync, "_search") as search:
            got = rawg_sync.resync_one(self.db, "g")
        search.assert_not_called()
        self.assertEqual(got["status"], "updated")
        self.assertEqual((self.game().release_date, self.game().image_url), (datetime.date(2026, 12, 11), "https://img/poe2.jpg"))
        self.assertEqual(self.game().name, "Path of Exile 2")

    def test_a_blank_value_from_rawg_never_blanks_ours(self):
        self.game().rawg_id = 391403
        self.game().dev = "Somebody"
        self.db.commit()
        with mock.patch.object(rawg_sync, "_details", return_value={**DETAILS, "dev": ""}):
            rawg_sync.resync_one(self.db, "g")
        self.assertEqual(self.game().dev, "Somebody")

    def test_an_unlinked_game_is_searched_by_name_and_linked(self):
        with mock.patch.object(rawg_sync, "_search", return_value=[{"id": 391403, "name": "Path of Exile 2", "slug": "path-of-exile-2"}]):
            got = rawg_sync.resync_one(self.db, "g")
        self.assertEqual(got["status"], "updated")
        self.assertEqual(self.game().rawg_id, 391403)

    def test_a_doubtful_match_returns_candidates_and_changes_nothing(self):
        with mock.patch.object(rawg_sync, "_search", return_value=[{"id": 1, "name": "Path of Exile", "slug": "path-of-exile"}]):
            got = rawg_sync.resync_one(self.db, "g")
        self.assertEqual(got["status"], "ambiguous")
        self.assertEqual(got["candidates"][0]["rawg_id"], 1)
        self.assertIsNone(self.game().rawg_id)

    def test_nothing_found_and_taken_ids_are_reported(self):
        with mock.patch.object(rawg_sync, "_search", return_value=[]):
            self.assertEqual(rawg_sync.resync_one(self.db, "g")["status"], "not_found")
        self.db.add(models.Game(id="o", name="Other", rawg_id=391403))
        self.db.commit()
        with mock.patch.object(rawg_sync, "_search", return_value=[{"id": 391403, "name": "Path of Exile 2", "slug": "x"}]):
            got = rawg_sync.resync_one(self.db, "g")
        self.assertEqual((got["status"], got["other_name"]), ("duplicate", "Other"))

    def test_no_key_and_unknown_game(self):
        with mock.patch.object(type(rawg_sync.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=""):
            with self.assertRaises(RuntimeError):
                rawg_sync.resync_one(self.db, "g")
        with self.assertRaises(LookupError):
            rawg_sync.resync_one(self.db, "nope")


class HltbResyncTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hades", avg_time=100))
        self.db.commit()

    def run_with(self, entries):
        with mock.patch.object(hltb_sync, "_search", return_value=entries):
            return hltb_sync.resync_one(self.db, "g")

    def test_a_clear_match_replaces_the_time(self):
        got = self.run_with([entry("Hades", 72000)])
        self.assertEqual((got["status"], self.db.get(models.Game, "g").avg_time), ("updated", 72000))
        self.assertEqual(self.run_with([entry("Hades", 72000)])["status"], "unchanged")

    def test_no_time_not_found_and_ambiguous_leave_the_time_alone(self):
        self.assertEqual(self.run_with([entry("Hades", 0)])["status"], "no_time")
        self.assertEqual(self.run_with([])["status"], "not_found")
        got = self.run_with([entry("Hades Star", 3600, 1), entry("Hades Star 2", 7200, 2)])
        self.assertIn(got["status"], ("ambiguous", "not_found"))
        self.assertEqual(self.db.get(models.Game, "g").avg_time, 100)


IGDB_DETAILS = {
    "igdb_id": 228525, "name": "Hades II", "slug": "hades-ii", "dev": "Supergiant Games", "steam_id": "1145350",
    "release_date": datetime.date(2025, 9, 25), "image_url": "https://img/h2.jpg", "genres": "Role-playing (RPG)", "is_dlc": False,
    "parent_igdb_id": None, "themes": "Fantasy", "keywords": "Roguelike", "franchises": "Hades", "collections": "Hades",
}


class IgdbResyncTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hades II", release_date=datetime.date(2025, 1, 1), image_url="old", dev="Old Dev", genres="RPG"))
        self.db.commit()
        for patcher in (
            mock.patch.object(igdb, "configured", return_value=True),
            mock.patch.object(igdb, "game_details", return_value=dict(IGDB_DETAILS)),
            mock.patch.object(igdb, "find_by_steam", return_value=[]),
            mock.patch.object(igdb, "search_items", return_value=[]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def game(self):
        return self.db.get(models.Game, "g")

    def test_a_linked_game_overwrites_what_igdb_gives_without_searching_and_never_the_name(self):
        self.game().igdb_id = 228525
        self.db.commit()
        got = igdb_sync.resync_one(self.db, "g")
        game = self.game()
        self.assertEqual(got["status"], "updated")
        self.assertEqual((game.dev, game.release_date, game.image_url, game.genres, game.steam_id), ("Supergiant Games", datetime.date(2025, 9, 25), "https://img/h2.jpg", "Role-playing (RPG)", "1145350"))
        self.assertEqual((game.themes, game.keywords, game.franchises, game.collections, game.slug), ("Fantasy", "Roguelike", "Hades", "Hades", "hades-ii"))
        self.assertEqual(game.name, "Hades II")
        self.assertEqual(igdb_sync.resync_one(self.db, "g")["status"], "unchanged")
        igdb.search_items.assert_not_called()

    def test_a_blank_never_overwrites_and_a_rawg_slug_is_kept(self):
        game = self.game()
        game.igdb_id, game.rawg_id, game.slug, game.steam_id = 228525, 5, "rawg-slug", "999"
        self.db.commit()
        igdb.game_details.return_value = dict(IGDB_DETAILS, dev=None, steam_id="", image_url=None)
        igdb_sync.resync_one(self.db, "g")
        game = self.game()
        self.assertEqual((game.dev, game.steam_id, game.image_url, game.slug), ("Old Dev", "999", "old", "rawg-slug"))

    def test_a_game_without_an_igdb_id_is_found_by_its_certain_match_and_linked(self):
        igdb.search_items.return_value = [{"id": 228525, "name": "Hades II", "first_release_date": 1758758400, "game_type": 0, "version_parent": None}]
        got = igdb_sync.resync_one(self.db, "g")
        self.assertEqual((got["status"], self.game().igdb_id), ("updated", 228525))
        self.assertIn("igdb_id", got["changed"])

    def test_a_doubtful_match_is_not_applied_and_comes_back_with_candidates(self):
        igdb.search_items.return_value = [{"id": 1, "name": "Hades", "first_release_date": 1600300800, "game_type": 0, "version_parent": None}]
        got = igdb_sync.resync_one(self.db, "g")
        self.assertEqual((got["status"], got["candidates"][0]["igdb_id"], self.game().igdb_id), ("ambiguous", 1, None))
        igdb.search_items.return_value = []
        self.assertEqual(igdb_sync.resync_one(self.db, "g")["status"], "not_found")

    def test_an_igdb_id_another_game_has_is_a_duplicate(self):
        self.db.add(models.Game(id="other", name="Hades 2", igdb_id=228525))
        self.db.commit()
        igdb.search_items.return_value = [{"id": 228525, "name": "Hades II", "first_release_date": 1758758400, "game_type": 0, "version_parent": None}]
        got = igdb_sync.resync_one(self.db, "g")
        self.assertEqual((got["status"], got["other_name"], self.game().igdb_id), ("duplicate", "Hades 2", None))

    def test_a_dlc_is_marked_and_linked_to_a_base_game_the_catalogue_has(self):
        self.db.add(models.Game(id="base", name="Base", igdb_id=700))
        self.game().igdb_id = 228525
        self.db.commit()
        igdb.game_details.return_value = dict(IGDB_DETAILS, is_dlc=True, parent_igdb_id=700)
        igdb_sync.resync_one(self.db, "g")
        self.assertEqual((self.game().is_dlc, self.game().parent_game_id), (True, "base"))

    def test_the_chosen_candidate_overwrites_when_asked_and_only_links_when_not(self):
        self.assertEqual(igdb_sync.apply_one(self.db, "g", 228525), {"linked": True, "changed": ["igdb_id"]})
        self.assertEqual(self.game().dev, "Old Dev")  # the batch only links and fills IGDB's own columns
        got = igdb_sync.apply_one(self.db, "g", 228525, overwrite=True)
        self.assertIn("dev", got["changed"])
        self.assertEqual(self.game().dev, "Supergiant Games")

    def test_without_credentials_or_for_an_unknown_game_it_says_so(self):
        with mock.patch.object(igdb, "configured", return_value=False):
            with self.assertRaises(RuntimeError):
                igdb_sync.resync_one(self.db, "g")
        with self.assertRaises(LookupError):
            igdb_sync.resync_one(self.db, "nope")


class ResyncEndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hades"))
        self.db.commit()

    def test_each_source_reports_on_its_own(self):
        with mock.patch.object(rawg_sync, "resync_one", side_effect=RuntimeError("No hay clave de RAWG configurada")), \
                mock.patch.object(igdb_sync, "resync_one", side_effect=igdb.IgdbError("IGDB did not answer")), \
                mock.patch.object(hltb_sync, "resync_one", return_value={"status": "updated", "seconds": 5}):
            got = games.resync_game("g", self.db)
        self.assertEqual(got["rawg"], {"status": "error", "error": "No hay clave de RAWG configurada"})
        self.assertEqual(got["igdb"], {"status": "error", "error": "IGDB did not answer"})
        self.assertEqual(got["hltb"]["status"], "updated")

    def test_igdb_goes_after_rawg_so_what_it_gives_wins_and_before_hltb(self):
        order = []
        with mock.patch.object(rawg_sync, "resync_one", side_effect=lambda *a: order.append("rawg") or {"status": "unchanged"}), \
                mock.patch.object(igdb_sync, "resync_one", side_effect=lambda *a: order.append("igdb") or {"status": "unchanged"}), \
                mock.patch.object(hltb_sync, "resync_one", side_effect=lambda *a: order.append("hltb") or {"status": "unchanged"}):
            games.resync_game("g", self.db)
        self.assertEqual(order, ["rawg", "igdb", "hltb"])

    def test_an_unknown_game_is_a_404(self):
        with self.assertRaises(HTTPException) as ctx:
            games.resync_game("nope", self.db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

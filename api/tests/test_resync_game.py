import datetime
import unittest
from unittest import mock

from fastapi import HTTPException

from src.database import models
from src.routers.manage import games
from src.utils import hltb_sync, rawg_sync
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


class ResyncEndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hades"))
        self.db.commit()

    def test_each_source_reports_on_its_own(self):
        with mock.patch.object(rawg_sync, "resync_one", side_effect=RuntimeError("No hay clave de RAWG configurada")), \
                mock.patch.object(hltb_sync, "resync_one", return_value={"status": "updated", "seconds": 5}):
            got = games.resync_game("g", self.db)
        self.assertEqual(got["rawg"], {"status": "error", "error": "No hay clave de RAWG configurada"})
        self.assertEqual(got["hltb"]["status"], "updated")

    def test_an_unknown_game_is_a_404(self):
        with self.assertRaises(HTTPException) as ctx:
            games.resync_game("nope", self.db)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

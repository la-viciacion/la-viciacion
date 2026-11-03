"""The app does not need RAWG (MariaDB required, see api_support.py). RAWG is the backup of IGDB and it has been down for days:
what a player or an admin does must work with no RAWG key at all, with a key and RAWG not answering, and the second must not
make anybody wait again and again. Every request to RAWG, in these tests, is a failure of the test."""
import datetime
from types import SimpleNamespace
from unittest import mock

import requests

from src.clients import igdb
from src.database import database, models
from src.utils import game_extras, hltb_sync, igdb_series, igdb_sync, my_utils, rawg_health, rawg_series, rawg_sync
from tests.api_support import ApiTestCase

IGDB_ID = 555
CANDIDATE = {
    "rawg_id": None, "igdb_id": IGDB_ID, "source": "igdb", "name": "Hades II", "slug": "hades-ii", "released": "2025-09-25",
    "image_url": "https://images.igdb.com/cover.jpg", "genres": ["Role-playing (RPG)"], "platforms": ["PC"], "dev": "Supergiant Games",
}
DETAILS = {
    "igdb_id": IGDB_ID, "name": "Hades II", "slug": "hades-ii", "igdb_slug": "hades-ii", "dev": "Supergiant Games", "steam_id": "",
    "release_date": datetime.date(2025, 9, 25), "image_url": "https://images.igdb.com/cover.jpg", "genres": "Role-playing (RPG)",
    "is_dlc": False, "parent_igdb_id": None, "themes": "Fantasy", "keywords": "Roguelike", "franchises": "Hades", "collections": "Hades",
    "perspectives": "Third person", "game_modes": "Single player",
}
MEDIA = {
    "url": "https://www.igdb.com/games/hades-ii", "description": "A roguelike.", "trailer": "abcdefghijk",
    "screenshots": [{"thumb": "https://images.igdb.com/igdb/image/upload/t_screenshot_med/a.jpg", "full": "https://images.igdb.com/igdb/image/upload/t_1080p/a.jpg"}],
    "critic": 93, "esrb": "Teen", "publishers": ["Supergiant Games"], "platforms": ["PC"],
}


class NoHltb:
    """HowLongToBeat knows nothing of any game, for the async search of a new game and the sync search of a resync."""

    def __init__(self, *args):
        pass

    async def async_search(self, name):
        return []

    def search(self, name, similarity_case_sensitive=True):
        return []


class WithoutRawgTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.root = self.user("root", admin=True)
        rawg_health.reset()
        self.addCleanup(rawg_health.reset)
        my_utils.reset_search_state()
        self.addCleanup(my_utils.reset_search_state)
        self.rawg_calls = mock.AsyncMock(side_effect=AssertionError("RAWG must not be asked"))
        self.igdb_search = mock.Mock(return_value=[dict(CANDIDATE)])
        for patcher in (
            mock.patch.object(type(my_utils.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=self.rawg_key()),
            mock.patch.object(my_utils, "_http_get", new=self.rawg_calls),
            mock.patch.object(rawg_sync, "requests", SimpleNamespace(get=mock.Mock(side_effect=AssertionError("RAWG must not be asked")), RequestException=requests.RequestException)),
            mock.patch.object(my_utils, "HowLongToBeat", new=NoHltb),
            mock.patch.object(hltb_sync, "HowLongToBeat", new=NoHltb),
            mock.patch.object(igdb, "configured", return_value=True),
            mock.patch.object(igdb, "search_games", self.igdb_search),
            mock.patch.object(igdb, "search_items", return_value=[]),
            mock.patch.object(igdb, "find_by_steam", return_value=[]),
            mock.patch.object(igdb, "game_details", side_effect=lambda igdb_id: dict(DETAILS) if igdb_id == IGDB_ID else None),
            mock.patch.object(igdb, "media_of", return_value=dict(MEDIA)),
            mock.patch.object(igdb, "series_of", return_value=[{"igdb_id": 1, "rawg_id": None, "name": "Hades", "slug": "hades", "image_url": None, "released": "2020-09-17"}]),
            mock.patch.object(igdb, "release_dates", return_value={}),
            mock.patch.object(igdb, "parent_of", return_value=None),
            mock.patch.object(igdb, "game_extras", side_effect=lambda igdb_id: {
                "themes": "Fantasy", "keywords": "", "franchises": "", "collections": "", "perspectives": "", "game_modes": "", "igdb_slug": "hades-ii",
            }),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        for module in (game_extras, igdb_series, rawg_series):
            module.clear()
            self.addCleanup(module.clear)

    def rawg_key(self):
        return ""

    def search(self, query="hades"):
        return self.api("GET", "/games/search", as_user="ana", params={"query": query})

    def create(self, **body):
        return self.api("POST", "/games/", as_user="ana", json={"name": "Hades II", "igdb_id": IGDB_ID, **body})


class WithoutRawgKeyTests(WithoutRawgTestCase):
    """No RAWG key: the whole life of a game, from the search to its page, without one request to RAWG."""

    def test_a_game_is_searched_created_and_shown_with_igdb_alone(self):
        found = self.search().json()
        self.assertEqual([(c["name"], c["igdb_id"], c["rawg_id"]) for c in found], [("Hades II", IGDB_ID, None)])
        created = self.create()
        self.assertEqual(created.status_code, 201)
        game = created.json()
        self.assertEqual((game["igdb_id"], game["rawg_id"], game["dev"], game["genres"]), (IGDB_ID, None, "Supergiant Games", "Role-playing (RPG)"))
        self.assertEqual(self.scalar("SELECT CONCAT_WS('|', igdb_slug, themes, perspectives, game_modes) FROM games"), "hades-ii|Fantasy|Third person|Single player")
        self.assertIsNotNone(self.scalar("SELECT created_at FROM games"))
        extras = self.api("GET", f"/games/{game['id']}/extras", as_user="ana").json()
        self.assertEqual((extras["available"], extras["trailer"]["youtube"], extras["metacritic"], extras["critic_source"], extras["publishers"]), (True, "abcdefghijk", 93, "igdb", ["Supergiant Games"]))
        saga = self.api("GET", f"/games/{game['id']}/series", as_user="ana").json()
        self.assertEqual((saga["available"], [g["name"] for g in saga["games"]]), (True, ["Hades", "Hades II"]))
        overview = self.api("GET", f"/games/{game['id']}/overview", as_user="ana").json()["game"]
        self.assertEqual(overview["links"], [{"name": "IGDB", "url": "https://www.igdb.com/games/hades-ii"}])
        self.rawg_calls.assert_not_awaited()

    def test_a_search_with_no_results_is_an_empty_list_and_not_an_error_or_a_warning(self):
        self.igdb_search.return_value = []
        with mock.patch.object(my_utils.logger, "warning") as warning, mock.patch.object(my_utils.logger, "error") as error:
            response = self.search("zzqxjv")
        self.assertEqual((response.status_code, response.json()), (200, []))
        warning.assert_not_called()
        error.assert_not_called()
        self.rawg_calls.assert_not_awaited()

    def test_a_query_that_is_too_long_for_any_game_is_refused_before_it_reaches_igdb(self):
        self.assertEqual(self.search("x" * 101).status_code, 400)
        self.assertEqual(self.search("x" * 100).status_code, 200)

    def test_when_igdb_fails_too_the_player_is_told_and_nobody_waits(self):
        self.igdb_search.side_effect = igdb.IgdbError("down")
        self.assertEqual(self.search().status_code, 503)
        self.assertEqual(self.search("hades 2").status_code, 503)  # IGDB is paused: no second wait
        self.assertEqual(self.igdb_search.call_count, 1)

    def test_the_resync_of_a_game_works_with_igdb_and_says_rawg_has_no_key(self):
        game_id = self.create().json()["id"]
        with mock.patch.object(igdb, "game_details", return_value=dict(DETAILS, dev="Supergiant")):
            body = self.api("POST", f"/manage/games/{game_id}/resync", as_user="root").json()
        self.assertEqual(body["igdb"]["status"], "updated")
        self.assertEqual(body["rawg"]["status"], "error")
        self.assertIn("RAWG", body["rawg"]["error"])
        self.assertEqual(self.scalar("SELECT dev FROM games"), "Supergiant")

    def test_the_wishlist_dates_the_batch_and_the_hourly_link_run_without_rawg(self):
        self.game("soon", "Soon", igdb_id=1, release_date=datetime.date.today() + datetime.timedelta(days=30))
        self.game("typed", "Typed", created_at=datetime.datetime.now(), release_date=datetime.date(2018, 1, 1))
        with database.SessionLocal() as db:
            games = [db.get(models.Game, "soon")]
            with mock.patch.object(igdb, "release_dates", return_value={1: datetime.date.today() + datetime.timedelta(days=45)}):
                changed, unanswered = igdb_sync.refresh_release_dates(db, games)
            self.assertEqual(([g.id for g in changed], unanswered), (["soon"], []))
            self.assertEqual(rawg_sync.refresh_release_dates(db, unanswered), [])  # no key, nothing to ask
            self.assertEqual(igdb_sync.link_recent(db), "0 linked of 1")
        self.rawg_calls.assert_not_awaited()

    def test_a_dlc_brings_its_base_game_from_igdb_alone(self):
        base = dict(DETAILS, igdb_id=700, name="Base Game", slug="base-game", igdb_slug="base-game", is_dlc=False)
        dlc = dict(DETAILS, igdb_id=701, name="Base Game: Expansion", slug="expansion", igdb_slug="expansion", is_dlc=True, parent_igdb_id=700)
        with mock.patch.object(igdb, "game_details", side_effect=lambda igdb_id: {700: base, 701: dlc}.get(igdb_id)):
            created = self.create(name="Base Game: Expansion", igdb_id=701).json()
        self.assertEqual((created["is_dlc"], created["parent_game_id"] is not None), (True, True))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games"), 2)


class RawgDownTests(WithoutRawgTestCase):
    """A RAWG key and RAWG not answering (what has been happening): the first request that has to ask it pays for the timeout,
    nothing after it does."""

    def rawg_key(self):
        return "a-key"

    def setUp(self):
        super().setUp()
        self.rawg_calls.side_effect = requests.Timeout("RAWG timed out")

    def test_an_empty_search_asks_rawg_once_and_then_leaves_it_alone_for_a_while(self):
        self.igdb_search.return_value = []
        self.assertEqual(self.search("zzqxjv").json(), [])
        self.assertEqual(self.rawg_calls.await_count, 1)
        self.assertTrue(rawg_health.paused())
        self.assertEqual(self.search("zzqxjw").json(), [])
        self.assertEqual(self.search("zzqxjx").json(), [])
        self.assertEqual(self.rawg_calls.await_count, 1)  # no more waiting

    def test_the_page_of_a_game_igdb_describes_never_waits_for_rawg(self):
        game_id = self.create().json()["id"]
        self.assertTrue(self.api("GET", f"/games/{game_id}/extras", as_user="ana").json()["available"])
        self.rawg_calls.assert_not_awaited()  # IGDB had it all

    def test_the_page_of_an_old_game_asks_rawg_once_and_the_next_game_not_at_all(self):
        self.game("old", "Old", rawg_id=1)
        self.game("older", "Older", rawg_id=2)
        self.assertFalse(self.api("GET", "/games/old/extras", as_user="ana").json()["available"])
        asked = self.rawg_calls.await_count
        self.assertGreaterEqual(asked, 1)
        self.assertFalse(self.api("GET", "/games/older/extras", as_user="ana").json()["available"])
        self.assertEqual(self.rawg_calls.await_count, asked)
        self.assertEqual(self.api("GET", "/games/old/series", as_user="ana").json(), {"available": False, "games": []})
        self.assertEqual(self.rawg_calls.await_count, asked)

    def test_the_resync_of_a_game_does_not_wait_for_a_rawg_that_is_down(self):
        game_id = self.create().json()["id"]
        rawg_health.failed()
        with mock.patch.object(rawg_sync.time, "sleep") as slept:
            body = self.api("POST", f"/manage/games/{game_id}/resync", as_user="root").json()
        self.assertEqual((body["rawg"]["status"], body["igdb"]["status"]), ("error", "unchanged"))
        slept.assert_not_called()

    def test_an_error_answer_or_a_fake_failure_is_not_a_reason_to_stop_asking(self):
        self.rawg_calls.side_effect = None
        self.rawg_calls.return_value = SimpleNamespace(ok=False, status_code=500, content=b"error", json=lambda: {})
        self.igdb_search.return_value = []
        self.search("one")
        self.search("two")
        self.assertEqual(self.rawg_calls.await_count, 2)
        self.assertFalse(rawg_health.paused())


class PauseTests(ApiTestCase):
    def test_the_pause_starts_after_a_failure_ends_by_itself_and_can_be_reset(self):
        rawg_health.reset()
        self.assertFalse(rawg_health.paused())
        rawg_health.failed()
        self.assertTrue(rawg_health.paused())
        with mock.patch.object(rawg_health.time, "monotonic", return_value=rawg_health.time.monotonic() + rawg_health.PAUSE_SECONDS + 1):
            self.assertFalse(rawg_health.paused())
        rawg_health.reset()
        self.assertFalse(rawg_health.paused())

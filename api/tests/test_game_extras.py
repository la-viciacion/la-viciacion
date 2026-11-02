"""The outside data of a game page: what is read from Steam and RAWG, how the two are merged and how long it is kept (no database)."""
import unittest
from unittest import mock

from src.utils import game_extras, outside_cache

STEAM_PAGE = {
    "short_description": "Un juego &quot;de culto&quot;.<br>Con <b>etiquetas</b>.",
    "movies": [
        {"name": "old", "thumbnail": "http://cdn.akamai.steamstatic.com/a.jpg", "mp4": {"480": "http://cdn.akamai.steamstatic.com/old.mp4"}},
        {"name": "main", "highlight": True, "thumbnail": "https://video.fastly.steamstatic.com/p.jpg", "mp4": {"480": "https://video.fastly.steamstatic.com/m480.mp4", "max": "https://video.fastly.steamstatic.com/mmax.mp4"}},
    ],
    "screenshots": [{"path_thumbnail": "https://shared.steamstatic.com/t1.jpg", "path_full": "https://shared.steamstatic.com/f1.jpg"}, {"path_full": "https://evil.example/x.jpg"}],
    "metacritic": {"score": 88},
}


class MediaUrlTests(unittest.TestCase):
    def test_only_trusted_hosts_and_always_https(self):
        self.assertEqual(game_extras.media_url("http://cdn.akamai.steamstatic.com/a.mp4"), "https://cdn.akamai.steamstatic.com/a.mp4")
        self.assertEqual(game_extras.media_url("https://media.rawg.io/x.jpg"), "https://media.rawg.io/x.jpg")
        for bad in ("https://evil.example/a.mp4", "https://notsteamstatic.com/a.mp4", "javascript:alert(1)", "//cdn.steamstatic.com/a", None, 5):
            self.assertIsNone(game_extras.media_url(bad), bad)

    def test_clean_text_drops_tags_and_entities(self):
        self.assertEqual(game_extras.clean_text("a &amp; b<br><b>c</b>  d"), "a & b c d")
        self.assertIsNone(game_extras.clean_text("  <br> "))
        self.assertIsNone(game_extras.clean_text(None))


class ParseSteamTests(unittest.TestCase):
    def test_a_movie_listed_only_as_streams_uses_its_mp4_path(self):
        movie = {"id": 256706951, "highlight": True, "thumbnail": "https://shared.akamai.steamstatic.com/p.jpg", "dash_h264": "https://video.akamai.steamstatic.com/a.mpd", "hls_h264": "https://video.akamai.steamstatic.com/a.m3u8"}
        out = game_extras.parse_steam({"movies": [movie]})
        self.assertEqual(out["trailer"], {"url": "https://cdn.akamai.steamstatic.com/steam/apps/256706951/movie480.mp4", "poster": "https://shared.akamai.steamstatic.com/p.jpg"})
        self.assertIsNone(game_extras.parse_steam({"movies": [{"id": 1}]})["trailer"])  # not a Steam movie entry

    def test_it_reads_the_description_the_highlighted_trailer_and_the_trusted_screenshots(self):
        out = game_extras.parse_steam(STEAM_PAGE)
        self.assertIn("de culto", out["description"])
        self.assertNotIn("<", out["description"])
        self.assertEqual(out["trailer"], {"url": "https://video.fastly.steamstatic.com/m480.mp4", "poster": "https://video.fastly.steamstatic.com/p.jpg"})
        self.assertEqual(out["screenshots"], [{"thumb": "https://shared.steamstatic.com/t1.jpg", "full": "https://shared.steamstatic.com/f1.jpg"}])
        self.assertEqual(out["metacritic"], 88)

    def test_missing_data_is_empty(self):
        out = game_extras.parse_steam(None)
        self.assertEqual(out, {"description": None, "trailer": None, "screenshots": [], "metacritic": None})
        self.assertIsNone(game_extras.parse_steam({"metacritic": {"score": 0}})["metacritic"])

    def test_the_screenshots_are_capped(self):
        shots = [{"path_full": f"https://x.steamstatic.com/{i}.jpg"} for i in range(20)]
        self.assertEqual(len(game_extras.parse_steam({"screenshots": shots})["screenshots"]), game_extras.MAX_SCREENSHOTS)


class ParseRawgTests(unittest.TestCase):
    def test_it_reads_the_rating_the_site_and_survives_nulls(self):
        out = game_extras.parse_rawg(
            {"metacritic": 77, "esrb_rating": {"name": "Mature"}},
            {"results": [{"preview": "https://media.rawg.io/p.jpg", "data": {"480": "https://media.rawg.io/v.mp4"}}]},
            {"results": [{"image": "https://media.rawg.io/s.jpg"}, None]},
        )
        self.assertEqual(out["metacritic"], 77)
        self.assertEqual(out["esrb"], "Mature")
        self.assertEqual(out["trailer"], {"url": "https://media.rawg.io/v.mp4", "poster": "https://media.rawg.io/p.jpg"})
        self.assertEqual(out["screenshots"], [{"thumb": "https://media.rawg.io/s.jpg", "full": "https://media.rawg.io/s.jpg"}])
        empty = game_extras.parse_rawg({"metacritic": None, "esrb_rating": None}, None, None)
        self.assertEqual(empty, {"description": None, "trailer": None, "screenshots": [], "metacritic": None, "esrb": None, "publishers": [], "platforms": []})


class RawgDetailTests(unittest.TestCase):
    def test_publishers_and_platforms_keep_rawgs_order_without_repeats_or_blanks(self):
        out = game_extras.parse_rawg({
            "description_raw": " A <b>big</b> game. ",
            "publishers": [{"name": "Rockstar Games"}, {"name": "Rockstar Games"}, {"name": " "}, None],
            "platforms": [{"platform": {"name": "PC"}}, {"platform": {"name": "PlayStation 4"}}, {"platform": None}, {"platform": {"name": "PC"}}],
        }, None, None)
        self.assertEqual(out["publishers"], ["Rockstar Games"])
        self.assertEqual(out["platforms"], ["PC", "PlayStation 4"])
        self.assertEqual(out["description"], "A big game.")

    def test_the_platforms_are_capped(self):
        many = [{"platform": {"name": f"P{i}"}} for i in range(30)]
        self.assertEqual(len(game_extras.parse_rawg({"platforms": many}, None, None)["platforms"]), game_extras.MAX_PLATFORMS)

    def test_nulls_leave_everything_empty(self):
        out = game_extras.parse_rawg({"description_raw": None, "publishers": None, "platforms": None}, None, None)
        self.assertEqual((out["description"], out["publishers"], out["platforms"]), (None, [], []))


class MergeTests(unittest.TestCase):
    def test_the_description_is_steams_in_spanish_or_else_rawgs_in_english(self):
        rawg = game_extras.parse_rawg({"description_raw": "English text"}, None, None)
        spanish = game_extras.merge(game_extras.parse_steam({"short_description": "Texto"}), rawg)
        english = game_extras.merge(game_extras.parse_steam(None), rawg)
        none = game_extras.merge(game_extras.parse_steam(None), game_extras.parse_rawg(None, None, None))
        self.assertEqual((spanish["description"], english["description"]), ("Texto", "English text"))
        self.assertIsNone(none["description"])

    def test_steam_leads_and_rawg_fills_in(self):
        steam = game_extras.parse_steam({"short_description": "hola"})
        rawg = game_extras.parse_rawg({"metacritic": 70, "esrb_rating": {"name": "Teen"}}, {"results": [{"data": {"max": "https://media.rawg.io/v.mp4"}}]}, None)
        out = game_extras.merge(steam, rawg)
        self.assertEqual((out["description"], out["metacritic"], out["esrb"]), ("hola", 70, "Teen"))
        self.assertEqual(out["trailer"]["url"], "https://media.rawg.io/v.mp4")


class FetchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        game_extras.clear()
        self.addCleanup(game_extras.clear)
        key = mock.patch.object(type(game_extras.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="k")
        key.start()
        self.addCleanup(key.stop)
        self.clock = [1000.0]
        clock = mock.patch.object(outside_cache.time, "time", side_effect=lambda: self.clock[0])
        clock.start()
        self.addCleanup(clock.stop)
        self.calls = []
        self.fail = set()

    def serve(self, **pages):
        """Answers by the kind of URL (appdetails, movies, screenshots, stores, or the RAWG game itself)."""
        async def get(url, params, timeout):
            self.calls.append(url)
            name = next((n for n in ("appdetails", "movies", "screenshots", "stores") if n in url), "game")
            if name in self.fail:
                return mock.Mock(ok=False, status_code=500, content=b"")
            body = pages.get(name, {})
            return mock.Mock(ok=True, status_code=200, content=b"", json=lambda: body)
        patcher = mock.patch.object(game_extras.my_utils, "_http_get", new=get)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_a_steam_game_asks_rawg_for_videos_and_pictures_only_when_steam_lacks_them(self):
        self.serve(appdetails={"10": {"data": STEAM_PAGE}}, game={"metacritic": 90})
        out = await game_extras.extras_of(5, "10")
        self.assertEqual(out["trailer"]["url"], "https://video.fastly.steamstatic.com/m480.mp4")
        self.assertEqual(out["metacritic"], 90)  # RAWG's first, then Steam's (88)
        self.assertFalse(any(u.endswith("/movies") or u.endswith("/screenshots") for u in self.calls))

    async def test_without_steam_media_rawg_provides_the_videos_and_pictures(self):
        self.serve(movies={"results": [{"data": {"480": "https://media.rawg.io/v.mp4"}}]}, screenshots={"results": [{"image": "https://media.rawg.io/s.jpg"}]})
        out = await game_extras.extras_of(5, None)
        self.assertEqual(out["trailer"]["url"], "https://media.rawg.io/v.mp4")
        self.assertEqual(len(out["screenshots"]), 1)
        self.assertEqual(len(self.calls), 4)  # the game, its stores (no Steam id), its movies, its screenshots

    async def test_a_game_without_a_steam_id_gets_it_from_the_stores_rawg_links(self):
        self.serve(stores={"results": [{"url": "https://store.steampowered.com/app/504230/Celeste/"}]}, appdetails={"504230": {"data": STEAM_PAGE}})
        out = await game_extras.extras_of(5, None)
        self.assertEqual(out["trailer"]["url"], "https://video.fastly.steamstatic.com/m480.mp4")
        self.assertTrue(any("appids" in u or "appdetails" in u for u in self.calls))

    async def test_a_game_with_a_steam_id_does_not_ask_the_stores(self):
        self.serve(appdetails={"10": {"data": STEAM_PAGE}})
        await game_extras.extras_of(5, "10")
        self.assertFalse(any(u.endswith("/stores") for u in self.calls))

    async def test_a_game_with_no_steam_page_in_the_stores_has_only_rawgs_data(self):
        self.serve(stores={"results": [{"url": "https://www.nintendo.com/x"}]}, game={"description_raw": "English", "metacritic": 80})
        out = await game_extras.extras_of(5, None)
        self.assertEqual((out["description"], out["metacritic"]), ("English", 80))
        self.assertFalse(any("steampowered" in u for u in self.calls))

    async def test_a_game_with_neither_id_is_not_asked(self):
        self.serve()
        self.assertIsNone(await game_extras.extras_of(None, None))
        self.assertIsNone(await game_extras.extras_of(None, ""))
        self.assertIsNone(await game_extras.extras_of(None, "not-a-number"))
        self.assertEqual(self.calls, [])

    async def test_without_a_rawg_key_only_steam_is_asked(self):
        self.serve(appdetails={"10": {"data": STEAM_PAGE}})
        with mock.patch.object(type(game_extras.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=""):
            self.assertIsNone(await game_extras.extras_of(5, None))
            out = await game_extras.extras_of(5, "10")
        self.assertEqual(out["metacritic"], 88)
        self.assertTrue(all("steampowered" in u for u in self.calls))

    async def test_it_is_kept_a_day_and_asked_again_after_it(self):
        self.serve(appdetails={"10": {"data": STEAM_PAGE}})
        await game_extras.extras_of(None, "10")
        count = len(self.calls)
        await game_extras.extras_of(None, "10")
        self.assertEqual(len(self.calls), count)
        self.clock[0] += game_extras.CACHE_SECONDS + 1
        await game_extras.extras_of(None, "10")
        self.assertEqual(len(self.calls), 2 * count)

    async def test_one_source_failing_still_gives_the_other_and_all_failing_is_none_for_a_few_minutes(self):
        self.serve(game={"metacritic": 60})
        self.fail = {"appdetails"}
        out = await game_extras.extras_of(5, "10")
        self.assertEqual(out["metacritic"], 60)
        # what Steam did not answer is asked again in a few minutes, not tomorrow
        asked = len(self.calls)
        await game_extras.extras_of(5, "10")
        self.assertEqual(len(self.calls), asked)
        self.fail = set()
        self.clock[0] += game_extras.FAILURE_SECONDS + 1
        await game_extras.extras_of(5, "10")
        self.assertGreater(len(self.calls), asked)
        game_extras.clear()
        self.fail = {"appdetails", "game"}
        self.calls.clear()
        self.assertIsNone(await game_extras.extras_of(5, "10"))
        asked = len(self.calls)
        await game_extras.extras_of(5, "10")
        self.assertEqual(len(self.calls), asked)  # the failure is remembered
        self.clock[0] += game_extras.FAILURE_SECONDS + 1
        await game_extras.extras_of(5, "10")
        self.assertEqual(len(self.calls), 2 * asked)

    async def test_a_network_error_never_raises(self):
        async def boom(url, params, timeout):
            raise RuntimeError("down")
        with mock.patch.object(game_extras.my_utils, "_http_get", new=boom):
            self.assertIsNone(await game_extras.extras_of(5, "10"))



if __name__ == "__main__":
    unittest.main()


IGDB_PAGE = {
    "description": "A roguelike.", "trailer": "abcdefghijk",
    "screenshots": [{"thumb": "https://images.igdb.com/igdb/image/upload/t_screenshot_med/a.jpg", "full": "https://images.igdb.com/igdb/image/upload/t_1080p/a.jpg"}],
    "critic": 93, "esrb": "Teen", "publishers": ["Supergiant Games"], "platforms": ["PC", "Switch"],
}


class ParseIgdbTests(unittest.TestCase):
    def test_it_reads_the_youtube_trailer_the_screenshots_and_the_critics(self):
        out = game_extras.parse_igdb(IGDB_PAGE)
        self.assertEqual(out["trailer"], {"url": None, "youtube": "abcdefghijk", "poster": "https://images.igdb.com/igdb/image/upload/t_1080p/a.jpg"})
        self.assertEqual((out["metacritic"], out["esrb"], out["publishers"], out["platforms"]), (93, "Teen", ["Supergiant Games"], ["PC", "Switch"]))
        self.assertEqual(out["screenshots"][0]["full"], "https://images.igdb.com/igdb/image/upload/t_1080p/a.jpg")

    def test_nothing_is_empty(self):
        out = game_extras.parse_igdb(None)
        self.assertEqual((out["description"], out["trailer"], out["screenshots"], out["metacritic"], out["publishers"]), (None, None, [], None, []))


class MergeWithIgdbTests(unittest.TestCase):
    def test_igdb_leads_for_everything_but_the_description_which_steam_has_in_spanish(self):
        steam = game_extras.parse_steam({"short_description": "Un roguelike.", "metacritic": {"score": 80}, "screenshots": [{"path_full": "https://shared.steamstatic.com/f1.jpg"}]})
        rawg = game_extras.parse_rawg({"metacritic": 70, "esrb_rating": {"name": "Mature"}, "publishers": [{"name": "RAWG Pub"}]}, None, None)
        out = game_extras.merge(steam, rawg, game_extras.parse_igdb(IGDB_PAGE))
        self.assertEqual(out["description"], "Un roguelike.")
        self.assertEqual((out["metacritic"], out["critic_source"], out["esrb"], out["publishers"]), (93, "igdb", "Teen", ["Supergiant Games"]))
        self.assertEqual(out["trailer"]["youtube"], "abcdefghijk")
        self.assertIn("igdb.com", out["screenshots"][0]["full"])

    def test_without_steams_description_igdbs_comes_before_rawgs_and_the_score_says_its_source(self):
        rawg = game_extras.parse_rawg({"description_raw": "RAWG text", "metacritic": 70}, None, None)
        out = game_extras.merge(game_extras.parse_steam(None), rawg, game_extras.parse_igdb(IGDB_PAGE))
        self.assertEqual(out["description"], "A roguelike.")
        rawg_only = game_extras.merge(game_extras.parse_steam(None), rawg)
        self.assertEqual((rawg_only["metacritic"], rawg_only["critic_source"]), (70, "metacritic"))


class IgdbFetchTests(unittest.IsolatedAsyncioTestCase):
    """The same recorder of RAWG and Steam as `FetchTests`, with IGDB in front."""

    serve = FetchTests.serve

    def setUp(self):
        FetchTests.setUp(self)
        self.media = mock.Mock(return_value=dict(IGDB_PAGE))
        for patcher in (
            mock.patch.object(game_extras.igdb, "configured", return_value=True),
            mock.patch.object(game_extras.igdb, "media_of", self.media),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_a_game_igdb_describes_fully_does_not_ask_rawg_at_all(self):
        self.serve(appdetails={"10": {"data": {"short_description": "Hola"}}})
        out = await game_extras.extras_of(5, "10", 99)
        self.assertEqual((out["description"], out["metacritic"], out["critic_source"]), ("Hola", 93, "igdb"))
        self.media.assert_called_once_with(99)
        self.assertEqual([u for u in self.calls if "api.rawg.io" in u], [])

    async def test_rawg_fills_only_what_igdb_and_steam_lack(self):
        self.media.return_value = dict(IGDB_PAGE, trailer=None)
        self.serve(movies={"results": [{"data": {"480": "https://media.rawg.io/v.mp4"}}]})
        out = await game_extras.extras_of(5, None, 99)
        self.assertEqual(out["trailer"]["url"], "https://media.rawg.io/v.mp4")
        self.assertTrue(any(u.endswith("/movies") for u in self.calls))
        self.assertFalse(any(u.endswith("/screenshots") for u in self.calls))  # IGDB had them
        self.assertFalse(any(u.endswith("/stores") for u in self.calls))  # the Steam id is not looked for in RAWG for an IGDB game

    async def test_igdb_failing_leaves_a_partial_answer_from_the_rest_and_nothing_at_all_is_none(self):
        self.media.side_effect = game_extras.igdb.IgdbError("down")
        self.serve(appdetails={"10": {"data": STEAM_PAGE}}, game={"metacritic": 70})
        out = await game_extras.extras_of(5, "10", 99)
        self.assertEqual(out["metacritic"], 70)
        game_extras.clear()
        self.fail = {"appdetails", "game"}
        self.serve()
        self.assertIsNone(await game_extras.extras_of(5, "10", 99))

    async def test_igdbs_own_page_comes_with_the_extras(self):
        self.media.return_value = dict(IGDB_PAGE, url="https://www.igdb.com/games/hades-ii")
        self.serve()
        out = await game_extras.extras_of(None, None, 99)
        self.assertEqual(out["igdb_url"], "https://www.igdb.com/games/hades-ii")

    async def test_a_game_with_only_an_igdb_id_is_asked_to_igdb_alone(self):
        self.serve()
        out = await game_extras.extras_of(None, None, 99)
        self.assertEqual((out["trailer"]["youtube"], self.calls), ("abcdefghijk", []))

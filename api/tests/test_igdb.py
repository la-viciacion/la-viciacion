import unittest
from unittest import mock

from src.clients import igdb
from src.utils import my_utils

def time_after_pause():
    return my_utils.time.monotonic() + my_utils.IGDB_PAUSE_SECONDS + 1


ITEM = {
    "id": 1022, "name": "The Legend of Zelda", "slug": "the-legend-of-zelda", "first_release_date": 509328000,
    "release_dates": [{"date": 509328000, "date_format": 0}],
    "cover": {"id": 1, "image_id": "co1uii"}, "genres": [{"name": "Adventure"}], "platforms": [{"name": "Wii"}],
    "involved_companies": [
        {"developer": True, "company": {"name": "Nintendo"}},
        {"developer": False, "company": {"name": "A Publisher"}},
    ],
}


def _response(body, status=200):
    return mock.Mock(ok=status < 400, status_code=status, json=mock.Mock(return_value=body))


class IgdbClientTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("TWITCH_CLIENT_ID", "id"), ("TWITCH_CLIENT_SECRET", "secret")):
            patcher = mock.patch.object(igdb.config.__class__, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        igdb._token = None

    def test_it_is_configured_only_with_both_values(self):
        self.assertTrue(igdb.configured())
        with mock.patch.object(igdb.config.__class__, "TWITCH_CLIENT_SECRET", ""):
            self.assertFalse(igdb.configured())

    def test_a_result_becomes_a_picker_candidate(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([ITEM, {"id": 2}]),
        ]) as post:
            [found] = igdb.search_games('zelda "breath"')
        self.assertEqual(
            found,
            {"rawg_id": None, "igdb_id": 1022, "source": "igdb", "name": "The Legend of Zelda", "slug": "the-legend-of-zelda",
             "released": "1986-02-21", "image_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co1uii.jpg",
             "genres": ["Adventure"], "platforms": ["Wii"], "dev": "Nintendo"},
        )
        self.assertIn(b'name ~ *"zelda \\"breath\\""*', post.call_args.kwargs["data"])
        self.assertEqual(post.call_args.kwargs["headers"], {"Client-ID": "id", "Authorization": "Bearer t"})

    def test_only_games_are_asked_for_and_the_exact_name_then_the_best_known_come_first(self):
        def item(name, count):
            return {"id": hash(name), "name": name, "total_rating_count": count}
        found = [item("The Wolf Among Us", 1225), item("Among Us", None), item("Among Us!", 600), item("Among Us VR", 50)]
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response(found),
        ]) as post:
            names = [c["name"] for c in igdb.search_games("among us")]
        self.assertEqual(names, ["Among Us!", "Among Us", "The Wolf Among Us", "Among Us VR"])
        self.assertIn(b'where name ~ *"among us"* & game_type = (0,8,9,10,11,1,2,3,4) & version_parent = null;', post.call_args.kwargs["data"])
        self.assertIn(b"sort total_rating_count desc", post.call_args.kwargs["data"])

    def test_the_details_of_a_game_are_in_the_shape_of_a_new_game(self):
        item = dict(ITEM, game_type=0, external_games=[
            {"external_game_source": 10, "uid": "yt"}, {"external_game_source": igdb.STEAM_SOURCE, "uid": "11949"},
        ])
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([item]),
        ]) as post:
            details = igdb.game_details(1022)
        self.assertIn(b"where id = 1022;", post.call_args.kwargs["data"])
        self.assertEqual(details["steam_id"], "11949")
        self.assertEqual(
            (details["igdb_id"], details["name"], details["dev"], details["genres"], details["is_dlc"]),
            (1022, "The Legend of Zelda", "Nintendo", "Adventure", False),
        )
        self.assertEqual(str(details["release_date"]), "1986-02-21")

    def test_the_themes_keywords_franchises_and_collections_come_with_the_details(self):
        item = dict(
            ITEM, game_type=0,
            themes=[{"name": "Fantasy"}, {"name": "4X (explore, expand, exploit, and exterminate)"}],
            keywords=[{"name": "Roguelike"}, {"name": "roguelike"}, {"name": "Hack, and slash"}],
            franchises=[{"name": "The Legend of Zelda"}], collections=[],
        )
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([item]),
        ]) as post:
            details = igdb.game_details(1022)
        self.assertIn(b"themes.name,keywords.name,franchises.name,collections.name", post.call_args.kwargs["data"])
        self.assertEqual(
            (details["themes"], details["keywords"], details["franchises"], details["collections"]),
            ("Fantasy,4X", "Roguelike,Hack and slash", "The Legend of Zelda", ""),
        )

    def test_the_perspectives_and_the_modes_of_a_game_come_with_its_data(self):
        item = dict(ITEM, game_type=0, player_perspectives=[{"name": "First person"}], game_modes=[{"name": "Single player"}, {"name": "Co-operative"}])
        with mock.patch.object(igdb.requests, "post", side_effect=[_response({"access_token": "t", "expires_in": 5000000}), _response([item])]) as post:
            details = igdb.game_details(1022)
        self.assertIn(b"player_perspectives.name,game_modes.name", post.call_args.kwargs["data"])
        self.assertEqual((details["perspectives"], details["game_modes"]), ("First person", "Single player,Co-operative"))

    def test_a_name_with_a_comma_never_splits_in_two(self):
        self.assertEqual(igdb.clean_name("4X (explore, expand, exploit, and exterminate)"), "4X")
        self.assertEqual(igdb.clean_name("Role-playing (RPG)"), "Role-playing (RPG)")
        self.assertEqual(igdb.clean_name("Rock, Paper,  Scissors"), "Rock Paper Scissors")

    def test_the_extras_of_a_linked_game_are_asked_by_id_and_a_game_igdb_lacks_is_none(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}),
            _response([{"id": 5, "themes": [{"name": "Horror"}]}]), _response([]),
        ]) as post:
            self.assertEqual(igdb.game_extras(5), {
                "themes": "Horror", "keywords": "", "franchises": "", "collections": "", "perspectives": "", "game_modes": "", "igdb_slug": "",
            })
            self.assertIsNone(igdb.game_extras(6))
        self.assertIn(b"where id = 5;", post.call_args_list[1].kwargs["data"])

    def test_the_series_of_a_game_are_the_other_games_of_its_collections_without_dlcs(self):
        collections = [{"games": [
            {"id": 1, "name": "Hades", "slug": "hades", "game_type": 0, "first_release_date": 1600300800, "cover": {"image_id": "cob9kr"}},
            {"id": 2, "name": "Hades II", "slug": "hades-ii", "game_type": 0, "first_release_date": 1758758400},
            {"id": 3, "name": "Hades Pack", "slug": "pack", "game_type": 13},
            {"id": 4, "name": "Hades Soundtrack DLC", "slug": "dlc", "game_type": 1},
        ]}, {"games": [{"id": 1, "name": "Hades", "slug": "hades", "game_type": 0}]}]
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([{"id": 2, "collections": collections}]), _response([]),
        ]):
            self.assertEqual(
                igdb.series_of(2),
                [{"igdb_id": 1, "rawg_id": None, "name": "Hades", "slug": "hades", "released": "2020-09-17",
                  "image_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/cob9kr.jpg"}],
            )
            self.assertIsNone(igdb.series_of(9))

    def test_only_an_exact_official_release_day_is_a_release_date(self):
        found = [
            {"id": 1, "release_dates": [{"date": 1789430400, "date_format": 0}, {"date": 1800000000, "date_format": 0}]},
            {"id": 2, "release_dates": [{"date": 1798675200, "date_format": 2}]},  # "2026": a placeholder day
            {"id": 3, "release_dates": []},
            {"id": 4, "release_dates": [{"date": 1600000000, "date_format": 0, "status": {"name": "Early Access"}}, {"date": 1700000000, "date_format": 0, "status": {"name": "Full Release"}}]},
            {"id": 5, "release_dates": [{"date": 1600000000, "date_format": 0, "status": {"name": "Beta"}}]},  # no launch yet
        ]
        with mock.patch.object(igdb.requests, "post", side_effect=[_response({"access_token": "t", "expires_in": 5000000}), _response(found)]) as post:
            dates = igdb.release_dates([1, 2, 3, 4, 5])
        self.assertEqual({k: str(v) for k, v in dates.items()}, {1: "2026-09-15", 4: "2023-11-14"})  # the earliest exact one that is a launch
        self.assertIn(b"where id = (1,2,3,4,5);", post.call_args.kwargs["data"])
        self.assertEqual(igdb.release_dates([]), {})

    def test_a_game_takes_its_official_launch_not_its_early_access_for_the_release_date(self):
        item = dict(ITEM, game_type=0, release_dates=[
            {"date": 1612224000, "date_format": 0, "status": {"name": "Early Access"}},  # 2021-02-02
            {"date": 1788998400, "date_format": 0, "status": {"name": "Full Release"}},  # 2026-09-10
        ])
        with mock.patch.object(igdb.requests, "post", side_effect=[_response({"access_token": "t", "expires_in": 5000000}), _response([item])]):
            self.assertEqual(str(igdb.game_details(1022)["release_date"]), "2026-09-10")
        self.assertIsNone(igdb.official_day({"release_dates": [{"date": 1612224000, "date_format": 0, "status": {"name": "Early Access"}}]}))
        self.assertIsNone(igdb.official_day({"release_dates": [{"date": 1798675200, "date_format": 2}]}))
        self.assertIsNone(igdb.official_day({}))

    def test_the_base_game_of_a_dlc_is_found_and_a_game_of_its_own_has_none(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}),
            _response([{"id": 5, "game_type": 1, "parent_game": {"id": 4, "name": "Base"}}]),
            _response([{"id": 4, "game_type": 0}]), _response([]),
        ]):
            self.assertEqual(igdb.parent_of(5), (4, "Base"))
            self.assertIsNone(igdb.parent_of(4))
            self.assertIsNone(igdb.parent_of(99))

    def test_a_dlc_brings_the_id_of_its_base_game_with_the_details(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([dict(ITEM, game_type=1, parent_game=4)]),
        ]):
            self.assertEqual(igdb.game_details(1022)["parent_igdb_id"], 4)

    def test_the_page_of_a_game_has_its_trailer_screenshots_critics_age_rating_publishers_and_platforms(self):
        item = {
            "id": 5, "summary": " A roguelike. ", "aggregated_rating": 93.5, "aggregated_rating_count": 17,
            "videos": [{"video_id": "bad id!", "name": "Trailer"}, {"video_id": "gameplay001", "name": "Gameplay"}, {"video_id": "trailerabc1", "name": "Launch Trailer"}],
            "screenshots": [{"image_id": f"s{n}"} for n in range(12)],
            "age_ratings": [
                {"rating_category": {"rating": "12", "organization": {"name": "PEGI"}}},
                {"rating_category": {"rating": "T", "organization": {"name": "ESRB"}}},
            ],
            "involved_companies": [{"publisher": True, "company": {"name": "Supergiant"}}, {"publisher": False, "company": {"name": "Dev Only"}}],
            "platforms": [{"name": "PC"}, {"name": "PC"}, {"name": "Switch"}],
        }
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([item]), _response([]),
        ]):
            media = igdb.media_of(5)
            self.assertIsNone(igdb.media_of(6))
        self.assertEqual((media["description"], media["trailer"], media["critic"], media["esrb"]), ("A roguelike.", "trailerabc1", 94, "Teen"))
        self.assertIsNone(media["url"])  # the fixture has none
        self.assertEqual((media["publishers"], media["platforms"], len(media["screenshots"])), (["Supergiant"], ["PC", "Switch"], 8))
        self.assertEqual(media["screenshots"][0], {
            "thumb": "https://images.igdb.com/igdb/image/upload/t_screenshot_med/s0.jpg", "full": "https://images.igdb.com/igdb/image/upload/t_1080p/s0.jpg",
        })

    def test_only_an_address_of_igdbs_own_pages_is_kept(self):
        for url, kept in (("https://www.igdb.com/games/hades-ii", True), ("https://evil.example/games/x", False), (None, False)):
            with mock.patch.object(igdb.requests, "post", side_effect=[_response({"access_token": "t", "expires_in": 5000000}), _response([{"id": 5, "url": url}])]):
                igdb._token = None
                self.assertEqual(igdb.media_of(5)["url"], url if kept else None)

    def test_without_critics_or_a_known_rating_those_are_none(self):
        item = {"id": 5, "aggregated_rating": 80.0, "age_ratings": [{"rating_category": {"rating": "EC", "organization": {"name": "ESRB"}}}]}
        with mock.patch.object(igdb.requests, "post", side_effect=[_response({"access_token": "t", "expires_in": 5000000}), _response([item])]):
            media = igdb.media_of(5)
        self.assertEqual((media["critic"], media["esrb"], media["trailer"], media["description"]), (None, None, None, None))  # no critic counted: a score alone is not trusted

    def test_a_dlc_is_marked_and_a_game_igdb_does_not_have_is_none(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([dict(ITEM, game_type=2)]), _response([]),
        ]):
            self.assertTrue(igdb.game_details(1)["is_dlc"])
            self.assertIsNone(igdb.game_details(2))

    def test_the_search_is_asked_only_when_no_name_contains_the_text(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([]), _response([ITEM]),
        ]) as post:
            [found] = igdb.search_games("zelda tears")
        self.assertEqual(found["name"], "The Legend of Zelda")
        contains, fuzzy = (c.kwargs["data"] for c in post.call_args_list[1:])
        self.assertIn(b'name ~ *"zelda tears"*', contains)
        self.assertIn(b'search "zelda tears";', fuzzy)

    def test_roman_numerals_count_as_digits_and_extras_come_after_the_games_proper(self):
        def item(name, game_type, count):
            return {"id": hash(name), "name": name, "game_type": game_type, "total_rating_count": count}
        found = [
            item("Alan Wake II: The Lake House", 1, 900), item("Alan Wake Remastered", 9, 400),
            item("Alan Wake II", 0, 300), item("Alan Wake II - Deluxe Bundle", 3, 800),
        ]
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response(found),
        ]) as post:
            names = [c["name"] for c in igdb.search_games("Alan Wake 2")]
        self.assertEqual(names, ["Alan Wake II", "Alan Wake Remastered", "Alan Wake II: The Lake House", "Alan Wake II - Deluxe Bundle"])
        self.assertIn(b"game_type = (0,8,9,10,11,1,2,3,4)", post.call_args.kwargs["data"])

    def test_the_result_is_cut_to_the_limit(self):
        found = [{"id": n, "name": f"Game {n}", "total_rating_count": n} for n in range(1, 21)]
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response(found),
        ]):
            self.assertEqual(len(igdb.search_games("game", limit=10)), 10)

    def test_the_token_is_asked_once_and_the_secret_never_goes_in_a_url(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([ITEM]), _response([ITEM]),
        ]) as post:
            igdb.search_games("a")
            igdb.search_games("b")
        token_calls = [c for c in post.call_args_list if c.args[0] == igdb.TOKEN_URL]
        self.assertEqual(len(token_calls), 1)
        self.assertNotIn("secret", token_calls[0].args[0])
        self.assertEqual(token_calls[0].kwargs["data"]["client_secret"], "secret")

    def test_a_revoked_token_is_renewed_once(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "old", "expires_in": 5000000}), _response({}, 401),
            _response({"access_token": "new", "expires_in": 5000000}), _response([ITEM]),
        ]):
            self.assertEqual(len(igdb.search_games("zelda")), 1)

    def test_a_rate_limit_is_tried_once_more_a_second_later_and_not_again(self):
        sleep = mock.patch.object(igdb.time, "sleep")
        with sleep as slept, mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response({}, 429), _response([ITEM]),
        ]):
            self.assertEqual(len(igdb.search_games("zelda")), 1)
        slept.assert_called_once_with(1.1)
        igdb._token = ("t", 2**40)
        with mock.patch.object(igdb.time, "sleep"), mock.patch.object(igdb.requests, "post", side_effect=[_response({}, 429), _response({}, 429)]):
            with self.assertRaises(igdb.IgdbError):
                igdb.search_games("zelda")

    def test_an_answer_that_is_not_what_it_should_be_is_an_igdb_error_and_never_a_stack_trace(self):
        igdb._token = None
        bad_token = mock.Mock(ok=True, status_code=200, json=mock.Mock(return_value={"unexpected": 1}))
        with mock.patch.object(igdb.requests, "post", return_value=bad_token):
            with self.assertRaises(igdb.IgdbError):
                igdb.search_games("zelda")
        igdb._token = ("t", 2**40)
        html = mock.Mock(ok=True, status_code=200, json=mock.Mock(side_effect=ValueError("not json")))
        with mock.patch.object(igdb.requests, "post", return_value=html):
            with self.assertRaises(igdb.IgdbError):
                igdb.search_games("zelda")

    def test_refused_credentials_and_errors_are_igdb_errors(self):
        with mock.patch.object(igdb.requests, "post", return_value=_response({}, 403)):
            with self.assertRaises(igdb.IgdbError):
                igdb.search_games("zelda")
        igdb._token = ("t", 2**40)
        with mock.patch.object(igdb.requests, "post", side_effect=igdb.requests.ConnectionError("secret in url")):
            with self.assertRaises(igdb.IgdbError) as raised:
                igdb.search_games("zelda")
        self.assertNotIn("secret", str(raised.exception))


class IgdbSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        my_utils.reset_search_state()
        self.addCleanup(my_utils.reset_search_state)

    async def test_the_completion_lookup_asks_howlongtobeat_and_not_rawg(self):
        class Hltb:
            async def async_search(self, name):
                return []
        with mock.patch.object(my_utils, "_http_get") as http, mock.patch.object(my_utils, "HowLongToBeat", Hltb):
            self.assertEqual(await my_utils.get_game_info("Hades"), {"hltb": None})
        http.assert_not_called()

    async def test_igdb_answers_first_and_rawg_is_not_asked_while_it_finds_games(self):
        candidate = igdb._candidate(ITEM)
        rawg = mock.AsyncMock()
        with mock.patch.object(my_utils, "_search_rawg", rawg), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", return_value=[candidate]):
            found = await my_utils.search_games("zelda")
        self.assertEqual([(c.name, c.rawg_id, c.source) for c in found], [("The Legend of Zelda", None, "igdb")])
        rawg.assert_not_awaited()

    async def test_rawg_is_asked_when_igdb_finds_nothing_and_its_failure_then_is_not_an_outage(self):
        rawg_candidate = my_utils.schemas.GameCandidate(rawg_id=1, name="Obscure", slug="obscure")
        with mock.patch.object(igdb, "configured", return_value=True), mock.patch.object(igdb, "search_games", return_value=[]):
            with mock.patch.object(my_utils, "_search_rawg", return_value=[rawg_candidate]):
                self.assertEqual([c.name for c in await my_utils.search_games("obscure")], ["Obscure"])
            my_utils.reset_search_state()
            with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.SearchUnavailable("down")):
                self.assertEqual(await my_utils.search_games("obscure"), [])

    async def test_rawg_answers_when_igdb_cannot(self):
        rawg_candidate = my_utils.schemas.GameCandidate(rawg_id=1, name="Zelda", slug="zelda")
        with mock.patch.object(my_utils, "_search_rawg", return_value=[rawg_candidate]), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", side_effect=igdb.IgdbError("down")):
            self.assertEqual([c.rawg_id for c in await my_utils.search_games("zelda")], [1])

    async def test_without_igdb_only_rawg_is_asked_and_its_outage_is_reported(self):
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.SearchUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=False), mock.patch.object(igdb, "search_games") as search:
            with self.assertRaises(my_utils.SearchUnavailable):
                await my_utils.search_games("zelda")
        search.assert_not_called()

    async def test_after_a_failure_igdb_is_not_waited_for_again_for_a_while(self):
        igdb_search = mock.Mock(side_effect=igdb.IgdbError("down"))
        with mock.patch.object(my_utils, "_search_rawg", return_value=[]), \
                mock.patch.object(igdb, "configured", return_value=True), mock.patch.object(igdb, "search_games", igdb_search):
            await my_utils.search_games("zelda")
            await my_utils.search_games("zelda 2")
            self.assertEqual(igdb_search.call_count, 1)
            with mock.patch.object(my_utils.time, "monotonic", return_value=time_after_pause()):
                await my_utils.search_games("zelda 3")
            self.assertEqual(igdb_search.call_count, 2)

    async def test_the_same_text_is_asked_once_and_the_marks_do_not_stay_in_the_answer(self):
        rawg = mock.AsyncMock(return_value=[my_utils.schemas.GameCandidate(rawg_id=1, name="Hades", slug="hades")])
        with mock.patch.object(my_utils, "_search_rawg", rawg), mock.patch.object(igdb, "configured", return_value=False):
            first = await my_utils.search_games("Hades")
            first[0].exists_in_db = True  # what mark_existing_games does
            second = await my_utils.search_games("  hades ")
        self.assertEqual(rawg.await_count, 1)
        self.assertFalse(second[0].exists_in_db)

    async def test_a_failure_is_not_remembered(self):
        rawg = mock.AsyncMock(side_effect=[my_utils.SearchUnavailable("down"), []])
        with mock.patch.object(my_utils, "_search_rawg", rawg), mock.patch.object(igdb, "configured", return_value=False):
            with self.assertRaises(my_utils.SearchUnavailable):
                await my_utils.search_games("zelda")
            self.assertEqual(await my_utils.search_games("zelda"), [])

    async def test_both_down_is_an_outage(self):
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.SearchUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", side_effect=igdb.IgdbError("down")):
            with self.assertRaises(my_utils.SearchUnavailable):
                await my_utils.search_games("zelda")


if __name__ == "__main__":
    unittest.main()

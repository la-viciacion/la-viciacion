import unittest
from unittest import mock

from src.clients import igdb
from src.utils import my_utils

def time_after_pause():
    return my_utils.time.monotonic() + my_utils.RAWG_PAUSE_SECONDS + 1


ITEM = {
    "id": 1022, "name": "The Legend of Zelda", "slug": "the-legend-of-zelda", "first_release_date": 509328000,
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

    def test_refused_credentials_and_errors_are_igdb_errors(self):
        with mock.patch.object(igdb.requests, "post", return_value=_response({}, 403)):
            with self.assertRaises(igdb.IgdbError):
                igdb.search_games("zelda")
        igdb._token = ("t", 2**40)
        with mock.patch.object(igdb.requests, "post", side_effect=igdb.requests.ConnectionError("secret in url")):
            with self.assertRaises(igdb.IgdbError) as raised:
                igdb.search_games("zelda")
        self.assertNotIn("secret", str(raised.exception))


class IgdbFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        my_utils.reset_search_state()
        self.addCleanup(my_utils.reset_search_state)

    async def test_igdb_answers_when_rawg_cannot(self):
        candidate = igdb._candidate(ITEM)
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.RawgUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", return_value=[candidate]):
            found = await my_utils.search_rawg_games("zelda")
        self.assertEqual([(c.name, c.rawg_id, c.source) for c in found], [("The Legend of Zelda", None, "igdb")])

    async def test_rawg_is_not_replaced_while_it_answers(self):
        with mock.patch.object(my_utils, "_search_rawg", return_value=[]), \
                mock.patch.object(igdb, "search_games") as search:
            self.assertEqual(await my_utils.search_rawg_games("zelda"), [])
        search.assert_not_called()

    async def test_without_igdb_the_outage_is_reported(self):
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.RawgUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=False):
            with self.assertRaises(my_utils.RawgUnavailable):
                await my_utils.search_rawg_games("zelda")

    async def test_after_a_failure_rawg_is_not_waited_for_again_for_a_while(self):
        rawg = mock.AsyncMock(side_effect=my_utils.RawgUnavailable("down"))
        with mock.patch.object(my_utils, "_search_rawg", rawg),                 mock.patch.object(igdb, "configured", return_value=True),                 mock.patch.object(igdb, "search_games", return_value=[igdb._candidate(ITEM)]):
            await my_utils.search_rawg_games("zelda")
            await my_utils.search_rawg_games("zelda 2")
            self.assertEqual(rawg.await_count, 1)
            with mock.patch.object(my_utils.time, "monotonic", return_value=time_after_pause()):
                await my_utils.search_rawg_games("zelda 3")
            self.assertEqual(rawg.await_count, 2)

    async def test_without_igdb_rawg_is_asked_every_time(self):
        rawg = mock.AsyncMock(side_effect=my_utils.RawgUnavailable("down"))
        with mock.patch.object(my_utils, "_search_rawg", rawg), mock.patch.object(igdb, "configured", return_value=False):
            for query in ("zelda", "zelda 2"):
                with self.assertRaises(my_utils.RawgUnavailable):
                    await my_utils.search_rawg_games(query)
        self.assertEqual(rawg.await_count, 2)

    async def test_the_same_text_is_asked_once_and_the_marks_do_not_stay_in_the_answer(self):
        rawg = mock.AsyncMock(return_value=[my_utils.schemas.RawgGameCandidate(rawg_id=1, name="Hades", slug="hades")])
        with mock.patch.object(my_utils, "_search_rawg", rawg):
            first = await my_utils.search_rawg_games("Hades")
            first[0].exists_in_db = True  # what mark_existing_games does
            second = await my_utils.search_rawg_games("  hades ")
        self.assertEqual(rawg.await_count, 1)
        self.assertFalse(second[0].exists_in_db)

    async def test_a_failure_is_not_remembered(self):
        rawg = mock.AsyncMock(side_effect=[my_utils.RawgUnavailable("down"), []])
        with mock.patch.object(my_utils, "_search_rawg", rawg), mock.patch.object(igdb, "configured", return_value=False):
            with self.assertRaises(my_utils.RawgUnavailable):
                await my_utils.search_rawg_games("zelda")
            self.assertEqual(await my_utils.search_rawg_games("zelda"), [])

    async def test_both_down_is_an_outage(self):
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.RawgUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", side_effect=igdb.IgdbError("down")):
            with self.assertRaises(my_utils.RawgUnavailable):
                await my_utils.search_rawg_games("zelda")


if __name__ == "__main__":
    unittest.main()

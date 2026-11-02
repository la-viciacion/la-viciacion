import unittest
from unittest import mock

from src.clients import igdb
from src.utils import my_utils

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
            {"rawg_id": None, "source": "igdb", "name": "The Legend of Zelda", "slug": "the-legend-of-zelda",
             "released": "1986-02-21", "image_url": "https://images.igdb.com/igdb/image/upload/t_cover_big/co1uii.jpg",
             "genres": ["Adventure"], "platforms": ["Wii"], "dev": "Nintendo"},
        )
        self.assertIn(b'search "zelda \\"breath\\"";', post.call_args.kwargs["data"])
        self.assertEqual(post.call_args.kwargs["headers"], {"Client-ID": "id", "Authorization": "Bearer t"})

    def test_the_token_is_asked_once_and_the_secret_never_goes_in_a_url(self):
        with mock.patch.object(igdb.requests, "post", side_effect=[
            _response({"access_token": "t", "expires_in": 5000000}), _response([]), _response([]),
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

    async def test_both_down_is_an_outage(self):
        with mock.patch.object(my_utils, "_search_rawg", side_effect=my_utils.RawgUnavailable("down")), \
                mock.patch.object(igdb, "configured", return_value=True), \
                mock.patch.object(igdb, "search_games", side_effect=igdb.IgdbError("down")):
            with self.assertRaises(my_utils.RawgUnavailable):
                await my_utils.search_rawg_games("zelda")


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest import mock

from src.utils import my_utils


class _Resp:
    ok = True

    def json(self):
        return {
            "results": [
                {"id": 1, "name": "Full", "slug": "full", "genres": [{"name": "Action"}],
                 "platforms": [{"platform": {"name": "PC"}}]},
                {"id": 2, "name": "Nulls", "slug": None, "genres": None, "platforms": None},
                {"id": 3, "name": "Odd", "slug": "odd", "genres": [{}], "platforms": [{"platform": None}]},
                {"id": None, "name": "No id", "slug": "no-id"},
            ]
        }


class RawgSearchNullsTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_fields_do_not_break_the_search(self):
        with mock.patch.object(my_utils.config.__class__, "RAWG_API_KEY", "k"), \
                mock.patch.object(my_utils, "_http_get", return_value=_Resp()):
            found = await my_utils.search_rawg_games("call of duty: modern")
        self.assertEqual([c.rawg_id for c in found], [1, 2, 3])
        self.assertEqual(found[0].platforms, ["PC"])
        self.assertEqual(found[1].genres, [])
        self.assertEqual(found[2].platforms, [])


if __name__ == "__main__":
    unittest.main()

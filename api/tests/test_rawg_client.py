import types
import unittest
from unittest import mock

from src.utils import rawg_sync


def answer(status=200, json_error=None, body=None):
    response = types.SimpleNamespace(status_code=status, ok=status < 400)
    def json():
        if json_error:
            raise json_error
        return body
    response.json = json
    return response


class ClientTests(unittest.TestCase):
    def get(self, response):
        with mock.patch.object(rawg_sync.requests, "get", return_value=response), mock.patch.object(rawg_sync.time, "sleep"):
            return rawg_sync._Client(5).get("/games/1")

    def test_a_json_answer_is_returned(self):
        self.assertEqual(self.get(answer(body={"released": "2026-11-01"})), {"released": "2026-11-01"})

    def test_a_200_that_is_not_json_is_a_connection_problem_not_a_crash(self):
        with self.assertRaises(ConnectionError):
            self.get(answer(json_error=ValueError("Expecting value")))


class RefreshReleaseDatesTests(unittest.TestCase):
    def test_a_page_that_is_not_json_skips_that_game_and_the_rest_are_still_refreshed(self):
        games = [types.SimpleNamespace(name="A", rawg_id=1, release_date=None), types.SimpleNamespace(name="B", rawg_id=2, release_date=None)]
        replies = iter([answer(json_error=ValueError("<html>")), answer(body={"released": "2026-11-01"})])
        with mock.patch.object(rawg_sync.config.__class__, "RAWG_API_KEY", "key"), \
                mock.patch.object(rawg_sync.requests, "get", side_effect=lambda *a, **k: next(replies)), \
                mock.patch.object(rawg_sync.time, "sleep"):
            changed = rawg_sync.refresh_release_dates(mock.Mock(), games)
        self.assertEqual([g.name for g in changed], ["B"])


if __name__ == "__main__":
    unittest.main()

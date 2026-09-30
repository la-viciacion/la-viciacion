import unittest
from unittest import mock

from src.utils import my_utils, rawg_sync, redaction

KEY = "abc123secret"
URL_ERROR = f"HTTPSConnectionPool: Max retries exceeded with url: /api/games?key={KEY}&search=doom"


class RedactionTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(redaction.config.__class__, "RAWG_API_KEY", KEY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_key_is_masked_wherever_it_appears(self):
        out = redaction.redact_rawg_key(URL_ERROR + " again " + KEY)
        self.assertNotIn(KEY, out)
        self.assertIn("key=***", out)

    def test_exceptions_and_bytes_are_accepted(self):
        self.assertNotIn(KEY, redaction.redact_rawg_key(RuntimeError(URL_ERROR)))
        self.assertNotIn(KEY, redaction.redact_rawg_key(URL_ERROR.encode()))

    def test_without_a_key_the_text_is_untouched(self):
        with mock.patch.object(redaction.config.__class__, "RAWG_API_KEY", ""):
            self.assertEqual(redaction.redact_rawg_key("plain"), "plain")


class LoggedErrorsTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_search_does_not_log_the_key(self):
        with mock.patch.object(redaction.config.__class__, "RAWG_API_KEY", KEY), \
                mock.patch.object(my_utils, "_http_get", side_effect=RuntimeError(URL_ERROR)), \
                mock.patch.object(my_utils.logger, "error") as error:
            self.assertEqual(await my_utils.search_rawg_games("doom"), [])
        logged = " ".join(str(c.args[0]) for c in error.call_args_list)
        self.assertIn("Error searching RAWG", logged)
        self.assertNotIn(KEY, logged)

    def test_the_sync_reuses_the_same_redaction(self):
        self.assertIs(rawg_sync.redact_rawg_key, redaction.redact_rawg_key)


if __name__ == "__main__":
    unittest.main()

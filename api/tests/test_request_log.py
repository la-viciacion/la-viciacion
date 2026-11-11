import asyncio
import logging
import unittest
from unittest import mock

from src.utils import request_context, request_log
from src.utils.logger import RETENTION_DAYS, _RequestTag


async def run(app, path="/api/v1/x", query=b"a=1", method="GET", client=("203.0.113.5", 5000)):
    scope = {"type": "http", "method": method, "path": path, "query_string": query, "client": client}
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    await request_log.RequestLogMiddleware(app, excluded_paths=["/api/v1/keepalive"])(scope, receive, send)
    return sent


def app_returning(status):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


class RequestLogTests(unittest.TestCase):
    def logged(self, coroutine):
        with mock.patch.object(request_log.logger, "info") as info:
            sent = asyncio.run(coroutine)
        return sent, [c.args[0] for c in info.call_args_list]

    def test_it_logs_method_path_query_status_and_duration(self):
        sent, lines = self.logged(run(app_returning(404)))
        self.assertEqual([m["type"] for m in sent], ["http.response.start", "http.response.body"])
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r'^REQUEST - "GET /api/v1/x\?a=1" - 404 - 0:00:00')

    def test_a_request_without_query_has_no_question_mark(self):
        _, lines = self.logged(run(app_returning(200), query=b""))
        self.assertIn('"GET /api/v1/x" - 200', lines[0])

    def test_the_value_of_a_sensitive_parameter_is_masked(self):
        _, lines = self.logged(run(app_returning(200), query=b"q=doom&token=abc123&api_key=zzz&monkey=1"))
        self.assertIn("?q=doom&token=***&api_key=***&monkey=1\"", lines[0])
        self.assertNotIn("abc123", lines[0])

    def test_the_keepalive_probe_is_not_logged(self):
        _, lines = self.logged(run(app_returning(200), path="/api/v1/keepalive"))
        self.assertEqual(lines, [])

    def test_a_crash_is_logged_as_500_and_still_raised(self):
        async def broken(scope, receive, send):
            raise RuntimeError("boom")

        with mock.patch.object(request_log.logger, "info") as info:
            with self.assertRaises(RuntimeError):
                asyncio.run(run(broken))
        self.assertIn("- 500 -", info.call_args.args[0])

    def test_other_protocols_pass_through(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        with mock.patch.object(request_log.logger, "info") as info:
            asyncio.run(request_log.RequestLogMiddleware(app)({"type": "lifespan"}, None, None))
        self.assertEqual(seen, ["lifespan"])
        info.assert_not_called()


class RequestContextTests(unittest.TestCase):
    def tag_during(self, app, **kwargs):
        seen = []

        async def watching(scope, receive, send):
            await app(scope, receive, send)
            seen.append(request_context.tag())

        with mock.patch.object(request_log.logger, "info"):
            asyncio.run(run(watching, **kwargs))
        return seen[0]

    def test_a_line_carries_request_id_player_and_address(self):
        async def logged_in(scope, receive, send):
            request_context.set_user("jose")
            await send({"type": "http.response.start", "status": 200, "headers": []})

        self.assertRegex(self.tag_during(logged_in), r"^\[[0-9a-f]{6} jose 203\.0\.113\.5\] $")

    def test_an_anonymous_request_shows_a_dash(self):
        self.assertRegex(self.tag_during(app_returning(200)), r"^\[[0-9a-f]{6} - 203\.0\.113\.5\] $")

    def test_the_player_set_in_a_worker_thread_reaches_the_request(self):
        async def threaded(scope, receive, send):
            await asyncio.to_thread(request_context.set_user, "ana")
            await send({"type": "http.response.start", "status": 200, "headers": []})

        self.assertIn(" ana ", self.tag_during(threaded))

    def test_nothing_is_tagged_outside_a_request(self):
        self.assertEqual(request_context.tag(), "")
        asyncio.run(run(app_returning(200)))
        self.assertEqual(request_context.tag(), "")

    def test_the_filter_stamps_the_record(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
        token = request_context.begin("10.0.0.1")
        try:
            _RequestTag().filter(record)
        finally:
            request_context.end(token)
        self.assertIn("10.0.0.1", record.request_tag)

    def test_the_files_are_kept_for_months(self):
        self.assertGreaterEqual(RETENTION_DAYS, 90)


if __name__ == "__main__":
    unittest.main()

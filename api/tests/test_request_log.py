import asyncio
import unittest
from unittest import mock

from src.utils import request_log


async def run(app, path="/api/v1/x", query=b"a=1", method="GET"):
    scope = {"type": "http", "method": method, "path": path, "query_string": query}
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


if __name__ == "__main__":
    unittest.main()

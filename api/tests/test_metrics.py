import asyncio
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.utils import metrics


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def build_app():
    app = FastAPI()

    @app.get("/api/v1/things/{thing_id}")
    def thing(thing_id: int):
        return {"id": thing_id}

    @app.get("/api/v1/boom")
    def boom():
        raise RuntimeError("boom")

    app.add_middleware(metrics.MetricsMiddleware)
    return app


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(build_app(), raise_server_exceptions=False)

    def count(self, route, status, method="GET"):
        return sample("laviciacion_http_requests_total", method=method, route=route, status=str(status))

    def test_a_request_is_counted_by_the_route_template_not_the_real_url(self):
        before = self.count("/api/v1/things/{thing_id}", 200)
        self.client.get("/api/v1/things/1")
        self.client.get("/api/v1/things/2")
        self.assertEqual(self.count("/api/v1/things/{thing_id}", 200), before + 2)
        self.assertNotIn("/api/v1/things/1", self.client.get("/metrics").text)

    def test_its_latency_is_recorded(self):
        before = sample("laviciacion_http_request_duration_seconds_count", method="GET", route="/api/v1/things/{thing_id}")
        self.client.get("/api/v1/things/1")
        after = sample("laviciacion_http_request_duration_seconds_count", method="GET", route="/api/v1/things/{thing_id}")
        self.assertEqual(after, before + 1)

    def test_every_unknown_path_shares_one_label(self):
        before = self.count(metrics.UNMATCHED, 404)
        self.client.get("/wp-login.php")
        self.client.get("/.env")
        self.assertEqual(self.count(metrics.UNMATCHED, 404), before + 2)
        self.assertNotIn("wp-login", self.client.get("/metrics").text)

    def test_a_crash_is_counted_as_a_500(self):
        before = self.count("/api/v1/boom", 500)
        self.assertEqual(self.client.get("/api/v1/boom").status_code, 500)
        self.assertEqual(self.count("/api/v1/boom", 500), before + 1)

    def test_metrics_are_exposed_in_prometheus_format_and_not_counted(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertIn("laviciacion_http_requests_total", response.text)
        self.assertEqual(sample("laviciacion_http_requests_total", method="GET", route=metrics.UNMATCHED, status="200"), 0)
        self.assertNotIn('route="/metrics"', response.text)

    def test_the_in_flight_gauge_returns_to_where_it_was(self):
        before = sample("laviciacion_http_requests_in_flight")
        self.client.get("/api/v1/things/1")
        self.client.get("/api/v1/boom")
        self.assertEqual(sample("laviciacion_http_requests_in_flight"), before)

    def test_only_get_serves_the_metrics_and_other_types_pass_through(self):
        self.assertEqual(self.client.post("/metrics").status_code, 404)

        async def lifespan_app(scope, receive, send):
            self.seen = scope["type"]

        asyncio.run(metrics.MetricsMiddleware(lifespan_app)({"type": "lifespan"}, None, None))
        self.assertEqual(self.seen, "lifespan")


class MainWiringTests(unittest.TestCase):
    """main.py opens the database on import, so its wiring is read from the source."""

    @classmethod
    def setUpClass(cls):
        with open(Path(__file__).parent.parent / "src" / "main.py", encoding="utf8") as source:
            cls.main = source.read()

    def test_the_middleware_is_added_after_the_others_so_it_is_the_outermost(self):
        self.assertIn("app.add_middleware(MetricsMiddleware)", self.main)
        added = self.main.index("app.add_middleware(MetricsMiddleware)")
        self.assertGreater(added, self.main.index("app.add_middleware(RequestLogMiddleware"))
        self.assertGreater(added, self.main.index("    CORSMiddleware,"))

    def test_the_metrics_path_is_outside_the_api_prefix(self):
        # the front's nginx only forwards /api/: that is what keeps /metrics inside the stack's network
        self.assertFalse(metrics.METRICS_PATH.startswith("/api"))

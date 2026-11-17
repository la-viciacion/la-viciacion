"""The admin's performance panel: how Prometheus' answers about the API's metrics become the panel's figures, and the route."""
import datetime
import unittest
from unittest import mock

from fastapi import HTTPException

from src.clients import prometheus
from src.clients.prometheus import PrometheusError
from src.routers.manage import performance as route
from src.utils import performance

URL = "http://p:9090"


def row(method, path, value):
    return ({"method": method, "route": path}, value)


class RouteTableTests(unittest.TestCase):
    def found(self):
        return {
            "count": [row("GET", "/a", 100), row("GET", "/b", 40), row("POST", "/c", 2), row("GET", "/d", 10)],
            "p95": [row("GET", "/a", 0.05), row("GET", "/b", 2.5), row("POST", "/c", 9.0)],
            "errors": [row("GET", "/b", 3)],
        }

    def test_the_slowest_are_ordered_by_p95_and_the_rarely_asked_are_left_out(self):
        slowest = performance.shape_routes(self.found())["slowest"]
        self.assertEqual([r["route"] for r in slowest], ["/b", "/a"])  # /c has 2 requests; /d has no p95

    def test_the_busiest_are_ordered_by_requests_with_their_errors(self):
        busiest = performance.shape_routes(self.found())["busiest"]
        self.assertEqual([(r["route"], r["requests"], r["errors"]) for r in busiest], [("/a", 100, 0), ("/b", 40, 3), ("/d", 10, 0)])
        self.assertIsNone(busiest[2]["p95"])

    def test_only_ten_routes_are_shown(self):
        many = {"count": [row("GET", f"/r{i}", 10 + i) for i in range(15)], "p95": [row("GET", f"/r{i}", i / 10) for i in range(15)], "errors": []}
        shaped = performance.shape_routes(many)
        self.assertEqual((len(shaped["slowest"]), len(shaped["busiest"])), (10, 10))


class ShapeTests(unittest.TestCase):
    def test_a_window_without_data_has_no_figures_but_zero_errors(self):
        now = performance.shape_now({"requests": None, "errors": None, "p50": None, "p95": None, "in_flight": None, "memory": None})
        self.assertEqual(now, {"requests": None, "errors": 0, "p50": None, "p95": None, "in_flight": None, "memory": None})

    def test_counts_are_rounded(self):
        now = performance.shape_now({"requests": 99.7, "errors": 2.2, "p50": 0.02, "p95": 0.4, "in_flight": 1.0, "memory": 3e8})
        self.assertEqual((now["requests"], now["errors"], now["in_flight"]), (100, 2, 1))

    def test_a_rate_is_taken_over_at_least_a_minute(self):
        self.assertIn("[60s]", performance.series_queries(30)["requests"])
        self.assertIn("[1800s]", performance.series_queries(1800)["p95"])


class KeepaliveTests(unittest.TestCase):
    def test_every_expression_over_requests_leaves_out_the_healthcheck(self):
        expressions = [*performance.now_queries(3600).values(), *performance.series_queries(300).values(), *performance.route_queries(3600).values()]
        about_requests = [e for e in expressions if "laviciacion_http_request" in e and "in_flight" not in e]
        self.assertGreaterEqual(len(about_requests), 10)
        for expression in about_requests:
            self.assertIn('route!~".*/keepalive"', expression)

    def test_the_errors_selector_keeps_its_status_filter(self):
        self.assertIn('status=~"5.."', performance.now_queries(60)["errors"])


class OverviewTests(unittest.TestCase):
    def setUp(self):
        performance.clear()
        self.addCleanup(performance.clear)

    def patched(self):
        return (
            mock.patch.object(prometheus, "instant", return_value=5.0),
            mock.patch.object(prometheus, "series", return_value=[[1000, 1.0]]),
            mock.patch.object(prometheus, "vector", return_value=[]),
        )

    def test_it_asks_for_the_tiles_the_charts_and_the_routes(self):
        instant, series, vector = self.patched()
        with instant as i, series as s, vector as v:
            data = performance.overview(URL, "24h")
        self.assertEqual(i.call_count, 6)
        self.assertEqual(s.call_count, 4)
        self.assertEqual(v.call_count, 3)
        self.assertEqual(set(data["charts"]), {"requests", "errors", "p95", "memory"})
        self.assertTrue(data["has_data"])
        self.assertEqual(data["window"], "24h")

    def test_the_answer_is_kept_a_minute_and_refresh_asks_again(self):
        instant, series, vector = self.patched()
        with instant as i, series, vector:
            performance.overview(URL, "1h")
            performance.overview(URL, "1h")
            self.assertEqual(i.call_count, 6)
            performance.overview(URL, "1h", refresh=True)
            self.assertEqual(i.call_count, 12)

    def test_each_window_is_kept_apart(self):
        instant, series, vector = self.patched()
        with instant as i, series, vector:
            performance.overview(URL, "1h")
            performance.overview(URL, "7d")
        self.assertEqual(i.call_count, 12)

    def test_no_requests_recorded_yet_says_so(self):
        with mock.patch.object(prometheus, "instant", return_value=None), mock.patch.object(prometheus, "series", return_value=[]), \
                mock.patch.object(prometheus, "vector", return_value=[]):
            data = performance.overview(URL, "30d")
        self.assertFalse(data["has_data"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        performance.clear()

    def test_without_prometheus_it_says_it_is_not_configured(self):
        with mock.patch.object(route.config.__class__, "PROMETHEUS_URL", new_callable=mock.PropertyMock, return_value=""):
            self.assertEqual(route.get_performance(window="24h", refresh=False), {"configured": False})

    def test_a_failure_of_prometheus_is_a_502(self):
        with mock.patch.object(route.config.__class__, "PROMETHEUS_URL", new_callable=mock.PropertyMock, return_value=URL), \
                mock.patch.object(performance, "overview", side_effect=PrometheusError("Prometheus no responde")):
            with self.assertRaises(HTTPException) as caught:
                route.get_performance(window="24h", refresh=False)
        self.assertEqual(caught.exception.status_code, 502)

    def test_it_is_an_admin_route(self):
        paths = {r.path: r for r in route.router.routes}
        names = {d.call.__name__ for d in paths["/manage/performance"].dependant.dependencies}
        self.assertIn("require_admin", names)


class ClientNumbersTests(unittest.TestCase):
    def reply(self, result):
        response = mock.Mock(status_code=200)
        response.ok = True
        response.json.return_value = {"status": "success", "data": {"result": result}}
        return response

    def test_nan_is_no_data(self):
        with mock.patch("requests.get", return_value=self.reply([{"metric": {}, "value": [1, "NaN"]}])):
            self.assertIsNone(prometheus.instant(URL, "x"))

    def test_a_series_leaves_out_the_points_with_no_number(self):
        values = [[1000, "1.5"], [1030, "NaN"], [1060, "2"]]
        start = datetime.datetime(2026, 1, 1)
        with mock.patch("requests.get", return_value=self.reply([{"metric": {}, "values": values}])):
            self.assertEqual(prometheus.series(URL, "x", start, start, 30), [[1000, 1.5], [1060, 2.0]])

    def test_a_vector_keeps_the_labels_and_drops_nan(self):
        result = [{"metric": {"route": "/a"}, "value": [1, "4"]}, {"metric": {"route": "/b"}, "value": [1, "NaN"]}]
        with mock.patch("requests.get", return_value=self.reply(result)):
            self.assertEqual(prometheus.vector(URL, "x"), [({"route": "/a"}, 4.0)])

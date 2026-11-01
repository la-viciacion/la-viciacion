"""The server panel: the Hetzner client, how its answers become the panel's figures, the cost estimate and the route."""
import datetime
import unittest
from unittest import mock

import requests
from fastapi import HTTPException

from src.clients import hetzner, prometheus
from src.clients.prometheus import PrometheusError
from src.clients.hetzner import HetznerError
from src.routers import server as route
from src.utils import server_status

TOKEN = "hcloud-FAKE-token-for-tests"
UTC = datetime.timezone.utc
TB = 10 ** 12


def answer(status=200, body=None):
    response = mock.Mock(status_code=status, reason="Reason")
    response.ok = status < 400
    response.json.return_value = body if body is not None else {}
    return response


def make_server(**changes) -> dict:
    server = {
        "id": 42, "name": "lavi", "status": "running", "created": "2025-06-01T08:00:00+00:00", "backup_window": None,
        "included_traffic": 20 * TB, "ingoing_traffic": 1000, "outgoing_traffic": 5 * TB,
        "location": {"name": "fsn1", "city": "Falkenstein", "country": "DE"},
        "server_type": {"name": "cx22", "cores": 2, "memory": 4.0, "disk": 40, "prices": [
            {"location": "nbg1", "price_hourly": {"gross": "0.0100"}, "price_monthly": {"gross": "9.9900"}, "price_per_tb_traffic": {"gross": "1.0000"}},
            {"location": "fsn1", "price_hourly": {"gross": "0.0080"}, "price_monthly": {"gross": "4.9000"}, "price_per_tb_traffic": {"gross": "1.2000"}},
        ]},
    }
    server.update(changes)
    return server


SERIES = {
    "cpu": {"values": [[1000, "12.5"], [1030, None], [1060, "7"]]},
    "network.0.bandwidth.in": {"values": [[1000, "100"]]},
    "network.0.bandwidth.out": {"values": [[1000, "200"]]},
    "disk.0.bandwidth.read": {"values": []},
}


class MetricsTests(unittest.TestCase):
    def test_values_come_as_numbers_and_holes_are_dropped(self):
        shaped = server_status.shape_metrics(SERIES)
        self.assertEqual(shaped["cpu"], [[1000, 12.5], [1060, 7.0]])
        self.assertEqual((shaped["net_in"], shaped["net_out"]), ([[1000, 100.0]], [[1000, 200.0]]))

    def test_a_series_hetzner_did_not_send_is_empty(self):
        self.assertEqual(server_status.shape_metrics(SERIES)["disk_write"], [])


class PriceTests(unittest.TestCase):
    def test_the_rate_is_the_plans_price_in_the_location_of_the_server(self):
        price = server_status.server_price(make_server())
        self.assertEqual(price["amount_cents"], 490)  # fsn1's 4,90, not nbg1's 9,99
        self.assertEqual(price["hourly_micros"], 8000)
        self.assertEqual((price["external_id"], price["name"], price["created"]), ("42", "Servidor lavi", datetime.date(2025, 6, 1)))

    def test_backups_add_a_fifth_to_both_prices(self):
        price = server_status.server_price(make_server(backup_window="22-02"))
        self.assertEqual((price["amount_cents"], price["hourly_micros"]), (588, 9600))

    def test_only_the_traffic_beyond_the_plan_is_charged(self):
        self.assertEqual(server_status.traffic_overage(make_server(outgoing_traffic=22 * TB)), 2.4)  # 2 TB * 1.20
        self.assertEqual(server_status.traffic_overage(make_server()), 0)


NOW_VALUES = {
    "memory_total": 4e9, "memory_available": 1e9, "disk_total": 40e9, "disk_available": 30e9,
    "load1": 0.5, "load5": 0.4, "load15": 0.3, "cores": 2.0, "uptime": 90061.9,
}
CHARTS = {"memory": [[1000, 75.0]], "disk": [[1000, 25.0]]}


class HostTests(unittest.TestCase):
    def test_memory_and_disk_are_what_is_used_of_the_total_with_their_series(self):
        host = server_status.shape_host(NOW_VALUES, CHARTS)
        self.assertEqual(host["memory"], {"used": 3e9, "total": 4e9, "series": [[1000, 75.0]]})
        self.assertEqual(host["disk"], {"used": 10e9, "total": 40e9, "series": [[1000, 25.0]]})
        self.assertEqual((host["load"], host["cores"], host["uptime"]), ([0.5, 0.4, 0.3], 2, 90061))

    def test_what_prometheus_has_no_data_for_is_left_out(self):
        host = server_status.shape_host({**NOW_VALUES, "disk_total": None, "load1": None, "cores": None, "uptime": None}, CHARTS)
        self.assertEqual((host["disk"], host["load"], host["cores"], host["uptime"]), (None, None, None, None))
        self.assertIsNotNone(host["memory"])


class PrometheusClientTests(unittest.TestCase):
    def test_an_instant_value_is_a_number_and_no_data_is_none(self):
        with mock.patch.object(prometheus.requests, "get", return_value=answer(body={"status": "success", "data": {"result": [{"value": [1, "2.5"]}]}})) as get:
            self.assertEqual(prometheus.instant("http://p:9090", "up"), 2.5)
        self.assertEqual(get.call_args.args[0], "http://p:9090/api/v1/query")
        with mock.patch.object(prometheus.requests, "get", return_value=answer(body={"status": "success", "data": {"result": []}})):
            self.assertIsNone(prometheus.instant("http://p:9090", "up"))

    def test_a_series_is_a_list_of_points(self):
        body = {"status": "success", "data": {"result": [{"values": [[1000, "1.23456"], [1030, "2"]]}]}}
        start, end = datetime.datetime(2026, 10, 1, tzinfo=UTC), datetime.datetime(2026, 10, 2, tzinfo=UTC)
        with mock.patch.object(prometheus.requests, "get", return_value=answer(body=body)) as get:
            self.assertEqual(prometheus.series("http://p:9090", "up", start, end, 30), [[1000, 1.235], [1030, 2.0]])
        self.assertEqual(get.call_args.kwargs["params"], {"query": "up", "start": start.timestamp(), "end": end.timestamp(), "step": 30})
        with mock.patch.object(prometheus.requests, "get", return_value=answer(body={"status": "success", "data": {"result": []}})):
            self.assertEqual(prometheus.series("http://p:9090", "up", start, end, 30), [])

    def test_a_refused_query_and_a_network_failure_are_errors(self):
        refused = answer(400, {"status": "error", "error": "parse error"})
        with mock.patch.object(prometheus.requests, "get", return_value=refused), self.assertRaises(PrometheusError) as caught:
            prometheus.instant("http://p:9090", "up(")
        self.assertIn("parse error", str(caught.exception))
        with mock.patch.object(prometheus.requests, "get", side_effect=requests.ConnectionError("boom")), self.assertRaises(PrometheusError):
            prometheus.instant("http://p:9090", "up")


class HostInStatusTests(unittest.TestCase):
    def setUp(self):
        server_status.clear()
        self.addCleanup(server_status.clear)
        patch = mock.patch.multiple(server_status.hetzner, server=mock.DEFAULT, metrics=mock.DEFAULT)
        self.hetzner = patch.start()
        self.addCleanup(patch.stop)
        self.hetzner["server"].return_value = make_server()
        self.hetzner["metrics"].return_value = SERIES

    def test_without_an_address_there_is_no_host_section_and_nobody_is_asked(self):
        with mock.patch.object(server_status.prometheus, "instant") as asked:
            self.assertIsNone(server_status.status(TOKEN, "42", "24h")["host"])
        asked.assert_not_called()

    def test_with_an_address_it_asks_prometheus_for_each_figure_over_the_same_window(self):
        values = iter(NOW_VALUES.values())
        with mock.patch.object(server_status.prometheus, "instant", side_effect=lambda *_: next(values)) as instant, \
                mock.patch.object(server_status.prometheus, "series", return_value=[[1000, 1.0]]) as series:
            host = server_status.status(TOKEN, "42", "7d", prometheus_url="http://p:9090")["host"]
        self.assertIsNotNone(host["memory"])
        self.assertEqual(instant.call_count, len(server_status.NOW_QUERIES))
        self.assertEqual(series.call_count, len(server_status.series_queries(1800)))
        _, _, start, end, step = series.call_args.args
        self.assertEqual(((end - start).total_seconds(), step), (7 * 86400, 1800))

    def test_prometheus_failing_fails_the_whole_answer_and_is_not_remembered(self):
        with mock.patch.object(server_status.prometheus, "instant", side_effect=PrometheusError("Prometheus no responde (ConnectionError)")), \
                self.assertRaises(PrometheusError):
            server_status.status(TOKEN, "42", "24h", prometheus_url="http://p:9090")
        values = iter(NOW_VALUES.values())
        with mock.patch.object(server_status.prometheus, "instant", side_effect=lambda *_: next(values)), \
                mock.patch.object(server_status.prometheus, "series", return_value=[]):
            self.assertIsNotNone(server_status.status(TOKEN, "42", "24h", prometheus_url="http://p:9090")["host"])

    def test_a_prometheus_that_knows_nothing_yet_is_an_error_that_names_node_exporter(self):
        with mock.patch.object(server_status.prometheus, "instant", return_value=None), self.assertRaises(PrometheusError) as caught:
            server_status.status(TOKEN, "42", "24h", prometheus_url="http://p:9090")
        self.assertIn("node-exporter", str(caught.exception))


class QueriesTests(unittest.TestCase):
    def test_a_rate_is_taken_over_as_long_as_a_point_of_the_chart_lasts_and_never_less_than_two_scrapes(self):
        self.assertIn("[60s]", server_status.series_queries(30)["cpu"])
        self.assertIn("[300s]", server_status.series_queries(300)["cpu"])
        self.assertIn("[7200s]", server_status.series_queries(7200)["disk_read"])

    def test_the_disk_ignores_the_virtual_devices(self):
        for key in ("disk_read", "disk_write"):
            self.assertIn("loop", server_status.series_queries(300)[key])


class WhereTheMetricsComeFromTests(unittest.TestCase):
    def setUp(self):
        server_status.clear()
        self.addCleanup(server_status.clear)
        patch = mock.patch.multiple(server_status.hetzner, server=mock.DEFAULT, metrics=mock.DEFAULT)
        self.hetzner = patch.start()
        self.addCleanup(patch.stop)
        self.hetzner["server"].return_value = make_server()
        self.hetzner["metrics"].return_value = SERIES

    def prometheus(self):
        values = iter(NOW_VALUES.values())
        by_name = {"cpu": [[1000, 3.0]], "disk_read": [[1000, 7.0]], "disk_write": [[1000, 9.0]]}
        names = iter(server_status.series_queries(300))

        def series(*_):
            return by_name.get(next(names), [[1000, 50.0]])

        return mock.patch.multiple(server_status.prometheus, instant=mock.Mock(side_effect=lambda *_: next(values)), series=mock.Mock(side_effect=series))

    def test_without_prometheus_hetzner_gives_the_cpu_and_the_disk_too(self):
        data = server_status.status(TOKEN, "42", "24h")
        self.assertEqual(self.hetzner["metrics"].call_args.args[5], "cpu,disk,network")
        self.assertEqual(data["metrics"]["cpu"], [[1000, 12.5], [1060, 7.0]])
        self.assertEqual(data["metrics"]["net_in"], [[1000, 100.0]])

    def test_with_prometheus_it_gives_the_cpu_and_the_disk_and_hetzner_only_the_network(self):
        with self.prometheus():
            data = server_status.status(TOKEN, "42", "24h", prometheus_url="http://p:9090")
        self.assertEqual(self.hetzner["metrics"].call_args.args[5], "network")
        self.assertEqual(data["metrics"]["cpu"], [[1000, 3.0]])
        self.assertEqual((data["metrics"]["disk_read"], data["metrics"]["disk_write"]), ([[1000, 7.0]], [[1000, 9.0]]))
        self.assertEqual((data["metrics"]["net_in"], data["metrics"]["net_out"]), ([[1000, 100.0]], [[1000, 200.0]]))


class DescribeTests(unittest.TestCase):
    def test_the_location_may_still_come_inside_a_datacenter(self):
        old = make_server()
        old["datacenter"] = {"location": old.pop("location")}
        self.assertEqual(server_status.describe(old)["location"], "Falkenstein, DE")
        self.assertEqual(server_status.server_price(old)["amount_cents"], 490)

    def test_it_keeps_what_the_group_may_see_and_not_the_address(self):
        server = make_server()
        server["public_net"] = {"ipv4": {"ip": "203.0.113.9"}}
        shown = server_status.describe(server)
        self.assertEqual((shown["name"], shown["status"], shown["location"]), ("lavi", "running", "Falkenstein, DE"))
        self.assertEqual(shown["traffic"], {"in": 1000, "out": 5 * TB, "included": 20 * TB})
        self.assertNotIn("203.0.113.9", str(shown))


class ClientTests(unittest.TestCase):
    def test_the_token_goes_only_in_the_header(self):
        with mock.patch.object(hetzner.requests, "get", return_value=answer(body={"server": {"id": 42}})) as get:
            self.assertEqual(hetzner.server(TOKEN, "42"), {"id": 42})
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": f"Bearer {TOKEN}"})
        self.assertNotIn(TOKEN, str(get.call_args.args) + str(get.call_args.kwargs.get("params")))

    def test_without_an_id_it_takes_the_only_server_of_the_project(self):
        with mock.patch.object(hetzner.requests, "get", return_value=answer(body={"servers": [{"id": 7}]})):
            self.assertEqual(hetzner.server(TOKEN, ""), {"id": 7})
        for servers in ([], [{"id": 1}, {"id": 2}]):
            with mock.patch.object(hetzner.requests, "get", return_value=answer(body={"servers": servers})), \
                    self.assertRaises(HetznerError) as caught:
                hetzner.server(TOKEN, "")
            self.assertIn("HETZNER_SERVER_ID", str(caught.exception))

    def test_a_refused_token_a_missing_server_and_other_errors_say_so(self):
        cases = ((401, {"error": {"message": "unable to authenticate"}}, "rechaza el token"), (404, {}, "HETZNER_SERVER_ID"), (500, {}, "500"))
        for status, body, expected in cases:
            with mock.patch.object(hetzner.requests, "get", return_value=answer(status, body)), self.assertRaises(HetznerError) as caught:
                hetzner.server(TOKEN, "42")
            self.assertIn(expected, str(caught.exception))

    def test_a_network_failure_never_carries_the_token(self):
        with mock.patch.object(hetzner.requests, "get", side_effect=requests.ConnectionError(f"boom {TOKEN}")), \
                self.assertRaises(HetznerError) as caught:
            hetzner.server(TOKEN, "42")
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_the_metrics_can_ask_for_the_network_alone(self):
        start, end = datetime.datetime(2026, 10, 1, tzinfo=UTC), datetime.datetime(2026, 10, 2, tzinfo=UTC)
        with mock.patch.object(hetzner.requests, "get", return_value=answer(body={"metrics": {"time_series": {}}})) as get:
            hetzner.metrics(TOKEN, 42, start, end, 300, hetzner.NETWORK_ONLY)
        self.assertEqual(get.call_args.kwargs["params"]["type"], "network")

    def test_the_metrics_ask_for_the_three_types_over_the_window(self):
        start, end = datetime.datetime(2026, 10, 1, tzinfo=UTC), datetime.datetime(2026, 10, 2, tzinfo=UTC)
        with mock.patch.object(hetzner.requests, "get", return_value=answer(body={"metrics": {"time_series": SERIES}})) as get:
            self.assertEqual(hetzner.metrics(TOKEN, 42, start, end, 300), SERIES)
        self.assertTrue(get.call_args.args[0].endswith("/servers/42/metrics"))
        self.assertEqual(get.call_args.kwargs["params"], {"type": "cpu,disk,network", "start": start.isoformat(), "end": end.isoformat(), "step": 300})


class StatusCacheTests(unittest.TestCase):
    def setUp(self):
        server_status.clear()
        self.addCleanup(server_status.clear)
        patch = mock.patch.multiple(server_status.hetzner, server=mock.DEFAULT, metrics=mock.DEFAULT)
        self.hetzner = patch.start()
        self.addCleanup(patch.stop)
        self.hetzner["server"].return_value = make_server()
        self.hetzner["metrics"].return_value = SERIES

    def test_it_asks_once_per_window_while_fresh_and_again_on_refresh(self):
        server_status.status(TOKEN, "42", "24h")
        server_status.status(TOKEN, "42", "24h")
        self.assertEqual(self.hetzner["server"].call_count, 1)
        server_status.status(TOKEN, "42", "7d")
        self.assertEqual(self.hetzner["server"].call_count, 2)
        server_status.status(TOKEN, "42", "24h", refresh=True)
        self.assertEqual(self.hetzner["server"].call_count, 3)

    def test_the_window_sets_how_far_back_and_how_often(self):
        server_status.status(TOKEN, "42", "7d")
        _, _, start, end, step, _ = self.hetzner["metrics"].call_args.args
        self.assertEqual((end - start).total_seconds(), 7 * 86400)
        self.assertEqual(step, 1800)

    def test_a_failure_is_not_remembered(self):
        self.hetzner["server"].side_effect = [HetznerError("down"), make_server()]
        with self.assertRaises(HetznerError):
            server_status.status(TOKEN, "42", "24h")
        server_status.status(TOKEN, "42", "24h")
        self.assertEqual(self.hetzner["server"].call_count, 2)


ITEMS = [{
    "kind": "server", "amount_cents": 490, "hourly_micros": 8000, "period": "month", "starts_on": datetime.date(2026, 1, 1), "ends_on": None,
}]


class RouteTests(unittest.TestCase):
    def setUp(self):
        server_status.clear()
        self.addCleanup(server_status.clear)
        self.admin, self.player = mock.Mock(is_admin=1), mock.Mock(is_admin=0)
        patch = mock.patch.object(route.costs_crud, "all_items", return_value=ITEMS)
        self.items = patch.start()
        self.addCleanup(patch.stop)

    def configured(self, token=TOKEN):
        return mock.patch.object(route, "config", mock.Mock(HETZNER_API_TOKEN=token, HETZNER_SERVER_ID="42", PROMETHEUS_URL=""))

    def test_without_a_token_it_says_it_is_not_configured_and_asks_nobody(self):
        with self.configured(""), mock.patch.object(server_status.hetzner, "server") as asked:
            self.assertEqual(route.get_status("24h", False, self.player, None), {"configured": False})
        asked.assert_not_called()

    def test_everybody_sees_the_state_and_the_cost_derived_from_the_rates(self):
        with self.configured(), mock.patch.object(server_status.hetzner, "server", return_value=make_server()), \
                mock.patch.object(server_status.hetzner, "metrics", return_value=SERIES):
            as_admin = route.get_status("24h", False, self.admin, None)
            as_player = route.get_status("24h", False, self.player, None)
        for answer in (as_admin, as_player):
            self.assertEqual(answer["server"]["status"], "running")
            self.assertEqual(answer["cost"]["total"]["since"], "2026-01-01")
            self.assertNotIn("overage", answer)

    def test_the_traffic_beyond_the_plan_is_added_to_the_running_month(self):
        with self.configured(), mock.patch.object(server_status.hetzner, "server", return_value=make_server(outgoing_traffic=22 * TB)), \
                mock.patch.object(server_status.hetzner, "metrics", return_value=SERIES), \
                mock.patch.object(route.costs, "summary", return_value={}) as summary:
            route.get_status("24h", False, self.player, None)
        self.assertEqual(summary.call_args.args[2], 2.4)

    def test_without_any_rate_yet_there_is_no_cost(self):
        self.items.return_value = []
        with self.configured(), mock.patch.object(server_status.hetzner, "server", return_value=make_server()), \
                mock.patch.object(server_status.hetzner, "metrics", return_value=SERIES):
            self.assertIsNone(route.get_status("24h", False, self.player, None)["cost"])

    def test_the_address_of_prometheus_goes_with_the_question(self):
        config = mock.Mock(HETZNER_API_TOKEN=TOKEN, HETZNER_SERVER_ID="42", PROMETHEUS_URL="http://p:9090")
        with mock.patch.object(route, "config", config), mock.patch.object(route.server_status, "status", return_value={"overage": 0.0}) as asked:
            route.get_status("24h", False, self.player, None)
        self.assertEqual(asked.call_args.kwargs["prometheus_url"], "http://p:9090")

    def test_only_an_admin_can_force_a_new_question(self):
        with self.configured(), mock.patch.object(server_status.hetzner, "server", return_value=make_server()) as asked, \
                mock.patch.object(server_status.hetzner, "metrics", return_value=SERIES):
            route.get_status("24h", False, self.player, None)
            route.get_status("24h", True, self.player, None)
            self.assertEqual(asked.call_count, 1)
            route.get_status("24h", True, self.admin, None)
            self.assertEqual(asked.call_count, 2)

    def test_a_prometheus_failure_is_a_502_too(self):
        config = mock.Mock(HETZNER_API_TOKEN=TOKEN, HETZNER_SERVER_ID="42", PROMETHEUS_URL="http://p:9090")
        with mock.patch.object(route, "config", config), \
                mock.patch.object(route.server_status, "status", side_effect=PrometheusError("Prometheus no responde (ConnectionError)")), \
                self.assertRaises(HTTPException) as caught:
            route.get_status("24h", False, self.player, None)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("Prometheus", caught.exception.detail)

    def test_a_failure_is_a_502_that_never_carries_the_token(self):
        with self.configured(), mock.patch.object(server_status.hetzner, "server", side_effect=HetznerError(f"rechazado {TOKEN}")), \
                self.assertRaises(HTTPException) as caught:
            route.get_status("24h", False, self.player, None)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn(TOKEN, caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

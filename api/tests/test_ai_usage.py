"""The spend of the AI: how OpenAI's daily buckets become the panel's figures, the client that asks for them and the route."""
import datetime
import unittest
from unittest import mock

import requests
from fastapi import HTTPException

from src.clients import openai_usage
from src.clients.ai_error import AIError
from src.routers.manage import ai_usage as route
from src.utils import ai_usage

KEY = "sk-admin-FAKE-key-for-tests"


def day(date: str, *results) -> dict:
    start = datetime.datetime.fromisoformat(date).replace(tzinfo=datetime.timezone.utc)
    return {"start_time": int(start.timestamp()), "results": [
        {"line_item": name, "amount": {"value": value, "currency": "usd"}} for name, value in results
    ]}


def answer(status=200, body=None, ok=None):
    response = mock.Mock(status_code=status, reason="Reason")
    response.ok = status < 400 if ok is None else ok
    response.json.return_value = body if body is not None else {}
    return response


class SummarizeTests(unittest.TestCase):
    def test_it_adds_up_the_total_each_month_and_each_line_item(self):
        data = ai_usage.summarize([
            day("2026-09-30", ("gpt-4.1-nano, input", 0.25), ("gpt-4.1-nano, output", 0.75)),
            day("2026-10-01", ("gpt-4.1-nano, input", 0.5)),
            day("2026-10-02", ("gpt-4.1-nano, input", 0.25), ("gpt-4.1-mini, output", 1.5)),
        ])
        self.assertEqual(data["total"], 3.25)
        self.assertEqual([m["month"] for m in data["months"]], ["2026-09", "2026-10"])
        self.assertEqual([m["total"] for m in data["months"]], [1.0, 2.25])
        self.assertEqual(data["items"][0], {"name": "gpt-4.1-mini, output", "amount": 1.5})  # the dearest first
        october = data["months"][1]["items"]
        self.assertEqual([i["name"] for i in october], ["gpt-4.1-mini, output", "gpt-4.1-nano, input"])
        self.assertEqual(data["days"], [
            {"date": "2026-09-30", "total": 1.0}, {"date": "2026-10-01", "total": 0.5}, {"date": "2026-10-02", "total": 1.75},
        ])
        self.assertEqual(data["currency"], "usd")

    def test_days_with_no_spend_are_left_out_and_nothing_at_all_is_zero(self):
        data = ai_usage.summarize([day("2026-10-01"), day("2026-10-02", ("x", 0)), {"start_time": 0, "results": None}])
        self.assertEqual((data["total"], data["months"], data["days"], data["items"]), (0, [], [], []))

    def test_a_day_is_the_utc_one_and_tiny_amounts_are_kept(self):
        data = ai_usage.summarize([day("2026-10-31", ("gpt-4.1-nano, input", 0.0000125))])
        self.assertEqual(data["months"][0]["month"], "2026-10")
        self.assertEqual(data["total"], 0.000013)  # rounded to 6 decimals

    def test_an_item_without_a_name_is_still_counted(self):
        data = ai_usage.summarize([{"start_time": 1790467200, "results": [{"amount": {"value": 1.5, "currency": "usd"}}]}])
        self.assertEqual(data["items"], [{"name": "Sin desglosar", "amount": 1.5}])


class ClientTests(unittest.TestCase):
    def test_it_follows_the_pages_and_sends_the_key_only_in_the_header(self):
        pages = [
            answer(body={"data": [day("2026-10-01")], "has_more": True, "next_page": "p2"}),
            answer(body={"data": [day("2026-10-02")], "has_more": False, "next_page": None}),
        ]
        with mock.patch.object(openai_usage.requests, "get", side_effect=pages) as get:
            buckets = openai_usage.costs(KEY, 0)
        self.assertEqual(len(buckets), 2)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["page"], "p2")
        self.assertNotIn("page", get.call_args_list[0].kwargs["params"])
        for call in get.call_args_list:
            self.assertEqual(call.kwargs["headers"], {"Authorization": f"Bearer {KEY}"})
            self.assertNotIn(KEY, str(call.args) + str(call.kwargs["params"]))

    def test_a_refused_key_says_so_with_what_openai_said(self):
        refused = answer(403, {"error": {"message": "Missing scopes: api.usage.read"}})
        with mock.patch.object(openai_usage.requests, "get", return_value=refused), self.assertRaises(AIError) as caught:
            openai_usage.costs(KEY, 0)
        self.assertIn("api.usage.read", str(caught.exception))

    def test_other_errors_and_a_network_failure_become_an_ai_error_without_the_key(self):
        with mock.patch.object(openai_usage.requests, "get", return_value=answer(500, {})), self.assertRaises(AIError) as caught:
            openai_usage.costs(KEY, 0)
        self.assertIn("500", str(caught.exception))
        with mock.patch.object(openai_usage.requests, "get", side_effect=requests.ConnectionError(f"boom {KEY}")), \
                self.assertRaises(AIError) as caught:
            openai_usage.costs(KEY, 0)
        self.assertNotIn(KEY, str(caught.exception))

    def test_a_cursor_that_never_ends_stops(self):
        endless = answer(body={"data": [], "has_more": True, "next_page": "again"})
        with mock.patch.object(openai_usage.requests, "get", return_value=endless) as get, self.assertRaises(AIError):
            openai_usage.costs(KEY, 0)
        self.assertEqual(get.call_count, openai_usage.MAX_PAGES)


class SummaryCacheTests(unittest.TestCase):
    def setUp(self):
        ai_usage.clear()
        self.addCleanup(ai_usage.clear)

    def test_it_asks_once_while_the_answer_is_fresh_and_again_on_refresh_or_when_it_expires(self):
        with mock.patch.object(ai_usage.openai_usage, "costs", return_value=[day("2026-10-01", ("x", 1.0))]) as costs:
            ai_usage.summary(KEY)
            ai_usage.summary(KEY)
            self.assertEqual(costs.call_count, 1)
            ai_usage.summary(KEY, refresh=True)
            self.assertEqual(costs.call_count, 2)
            with mock.patch.object(ai_usage.time, "time", return_value=ai_usage.time.time() + ai_usage.CACHE_SECONDS + 1):
                ai_usage.summary(KEY)
            self.assertEqual(costs.call_count, 3)

    def test_it_asks_from_the_oldest_day_openai_still_has_at_midnight_utc(self):
        now = datetime.datetime(2026, 10, 27, 15, 30, tzinfo=datetime.timezone.utc)
        start = datetime.datetime.fromtimestamp(ai_usage.first_day(now), tz=datetime.timezone.utc)
        self.assertEqual(start, datetime.datetime(2025, 10, 28, tzinfo=datetime.timezone.utc))
        self.assertLess((now - start).days, 365)  # OpenAI refuses 365 days or more
        with mock.patch.object(ai_usage.openai_usage, "costs", return_value=[]) as costs:
            ai_usage.summary(KEY)
        self.assertEqual(costs.call_args.args[0], KEY)
        self.assertLess(costs.call_args.args[1], int(datetime.datetime.now(datetime.timezone.utc).timestamp()))

    def test_a_failure_is_not_remembered(self):
        with mock.patch.object(ai_usage.openai_usage, "costs", side_effect=[AIError("down"), []]) as costs:
            with self.assertRaises(AIError):
                ai_usage.summary(KEY)
            ai_usage.summary(KEY)
        self.assertEqual(costs.call_count, 2)


class RouteTests(unittest.TestCase):
    def setUp(self):
        ai_usage.clear()
        self.addCleanup(ai_usage.clear)

    def test_without_the_admin_key_it_says_it_is_not_configured_and_asks_nobody(self):
        with mock.patch.object(route.settings, "get", return_value=None), mock.patch.object(ai_usage.openai_usage, "costs") as costs:
            self.assertEqual(route.get_ai_usage(), {"configured": False})
        costs.assert_not_called()

    def test_with_the_key_it_answers_the_summary(self):
        with mock.patch.object(route.settings, "get", return_value=KEY), \
                mock.patch.object(ai_usage.openai_usage, "costs", return_value=[day("2026-10-01", ("x", 2.0))]):
            result = route.get_ai_usage()
        self.assertTrue(result["configured"])
        self.assertEqual((result["provider"], result["total"]), ("openai", 2.0))

    def test_a_failure_is_a_502_that_never_carries_the_key(self):
        with mock.patch.object(route.settings, "get", return_value=KEY), \
                mock.patch.object(ai_usage.openai_usage, "costs", side_effect=AIError(f"rechazada {KEY}")), \
                self.assertRaises(HTTPException) as caught:
            route.get_ai_usage()
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn(KEY, caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

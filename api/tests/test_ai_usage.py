"""The spend of the AI: how the daily buckets of OpenAI and Anthropic become the panel's figures, the clients that ask for them and the route."""
import datetime
import unittest
from unittest import mock

import requests
from fastapi import HTTPException

from src.clients import anthropic_usage, openai_usage
from src.clients.ai_error import AIError
from src.routers.manage import ai_usage as route
from src.utils import ai_usage

KEY = "sk-admin-FAKE-key-for-tests"
ANTHROPIC_KEY = "sk-ant-admin01-FAKE-key-for-tests"


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
            self.assertEqual(route.get_ai_usage(provider="openai"), {"configured": False, "provider": "openai", "provider_key": False})
        costs.assert_not_called()

    def test_with_the_key_it_answers_the_summary(self):
        with mock.patch.object(route.settings, "get", return_value=KEY), \
                mock.patch.object(ai_usage.openai_usage, "costs", return_value=[day("2026-10-01", ("x", 2.0))]):
            result = route.get_ai_usage(provider="openai")
        self.assertTrue(result["configured"])
        self.assertEqual((result["provider"], result["total"]), ("openai", 2.0))

    def test_a_failure_is_a_502_that_never_carries_the_key(self):
        with mock.patch.object(route.settings, "get", return_value=KEY), \
                mock.patch.object(ai_usage.openai_usage, "costs", side_effect=AIError(f"rechazada {KEY}")), \
                self.assertRaises(HTTPException) as caught:
            route.get_ai_usage(provider="openai")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn(KEY, caught.exception.detail)


def anthropic_day(date: str, *results) -> dict:
    """A bucket as Anthropic's cost report gives it: RFC 3339 times and `amount` in cents, as a decimal string."""
    start = datetime.datetime.fromisoformat(date).replace(tzinfo=datetime.timezone.utc)
    return {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": (start + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": [{"amount": cents, "currency": "USD", "description": name, "model": None, "workspace_id": None} for name, cents in results],
    }


class AnthropicClientTests(unittest.TestCase):
    def test_its_buckets_come_in_the_shape_of_openais_with_dollars_and_the_description_as_the_line_item(self):
        page = answer(body={"data": [anthropic_day("2026-10-01", ("Claude Haiku 5.5 Usage - Input Tokens", "123.45"), ("Web Search Usage", "50"))], "has_more": False})
        with mock.patch.object(anthropic_usage.requests, "get", return_value=page):
            buckets = anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertEqual(buckets, [day("2026-10-01", ("Claude Haiku 5.5 Usage - Input Tokens", 1.2345), ("Web Search Usage", 0.5))])
        data = ai_usage.summarize(buckets)  # and the shared summary reads it
        self.assertEqual((data["total"], data["months"][0]["month"], data["currency"]), (1.7345, "2026-10", "usd"))

    def test_it_asks_for_the_days_grouped_by_description_with_the_key_in_the_header_only(self):
        with mock.patch.object(anthropic_usage.requests, "get", return_value=answer(body={"data": []})) as get:
            anthropic_usage.costs(ANTHROPIC_KEY, 1_700_000_000)
        params, headers = get.call_args.kwargs["params"], get.call_args.kwargs["headers"]
        self.assertEqual((params["starting_at"], params["bucket_width"], params["group_by[]"], params["limit"]), ("2023-11-14T22:13:20Z", "1d", "description", 31))
        self.assertEqual((headers["x-api-key"], headers["anthropic-version"]), (ANTHROPIC_KEY, anthropic_usage.VERSION))
        self.assertNotIn(ANTHROPIC_KEY, str(get.call_args.args) + str(params))

    def test_it_follows_the_pages(self):
        pages = [
            answer(body={"data": [anthropic_day("2026-10-01", ("x", "100"))], "has_more": True, "next_page": "page_2"}),
            answer(body={"data": [anthropic_day("2026-10-02", ("x", "100"))], "has_more": False, "next_page": None}),
        ]
        with mock.patch.object(anthropic_usage.requests, "get", side_effect=pages) as get:
            buckets = anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertEqual(len(buckets), 2)
        self.assertNotIn("page", get.call_args_list[0].kwargs["params"])
        self.assertEqual(get.call_args_list[1].kwargs["params"]["page"], "page_2")

    def test_days_with_no_costs_and_costs_with_no_description_are_read(self):
        page = answer(body={"data": [anthropic_day("2026-10-01"), {"starting_at": "2026-10-02T00:00:00Z", "results": [{"amount": "200", "currency": "USD"}]}], "has_more": False})
        with mock.patch.object(anthropic_usage.requests, "get", return_value=page):
            data = ai_usage.summarize(anthropic_usage.costs(ANTHROPIC_KEY, 0))
        self.assertEqual((data["total"], data["items"]), (2.0, [{"name": "Sin desglosar", "amount": 2.0}]))

    def test_a_refused_key_says_so_with_what_anthropic_said(self):
        refused = answer(403, {"type": "error", "error": {"type": "permission_error", "message": "This endpoint requires an Admin API key"}})
        with mock.patch.object(anthropic_usage.requests, "get", return_value=refused), self.assertRaises(AIError) as caught:
            anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertIn("Admin API key", str(caught.exception))
        self.assertNotIn(ANTHROPIC_KEY, str(caught.exception))

    def test_other_errors_a_network_failure_and_a_report_that_is_not_understood_are_ai_errors_without_the_key(self):
        with mock.patch.object(anthropic_usage.requests, "get", return_value=answer(529, {})), self.assertRaises(AIError) as caught:
            anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertIn("529", str(caught.exception))
        with mock.patch.object(anthropic_usage.requests, "get", side_effect=requests.ConnectionError(f"boom {ANTHROPIC_KEY}")), self.assertRaises(AIError) as caught:
            anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertNotIn(ANTHROPIC_KEY, str(caught.exception))
        for broken in ({"data": [{"results": []}]}, {"data": [{"starting_at": "not a date", "results": []}]}, {"data": [{"starting_at": "2026-10-01T00:00:00Z", "results": [{"amount": "x"}]}]}):
            with self.subTest(broken=broken), mock.patch.object(anthropic_usage.requests, "get", return_value=answer(body=broken)), self.assertRaises(AIError):
                anthropic_usage.costs(ANTHROPIC_KEY, 0)

    def test_a_cursor_that_never_ends_stops(self):
        endless = answer(body={"data": [], "has_more": True, "next_page": "again"})
        with mock.patch.object(anthropic_usage.requests, "get", return_value=endless) as get, self.assertRaises(AIError):
            anthropic_usage.costs(ANTHROPIC_KEY, 0)
        self.assertEqual(get.call_count, anthropic_usage.MAX_PAGES)


class PerProviderTests(unittest.TestCase):
    def setUp(self):
        ai_usage.clear()
        self.addCleanup(ai_usage.clear)

    def test_each_provider_is_asked_with_its_own_client_and_remembered_apart(self):
        with mock.patch.object(ai_usage.openai_usage, "costs", return_value=[day("2026-10-01", ("a", 1.0))]) as openai_costs, \
                mock.patch.object(ai_usage.anthropic_usage, "costs", return_value=[day("2026-10-01", ("b", 2.0))]) as anthropic_costs:
            self.assertEqual(ai_usage.summary(KEY)["total"], 1.0)
            self.assertEqual(ai_usage.summary(ANTHROPIC_KEY, provider="anthropic")["total"], 2.0)
            ai_usage.summary(KEY)
            ai_usage.summary(ANTHROPIC_KEY, provider="anthropic")
        self.assertEqual((openai_costs.call_count, anthropic_costs.call_count), (1, 1))
        self.assertEqual(anthropic_costs.call_args.args[0], ANTHROPIC_KEY)

    def test_a_refresh_or_a_failure_of_one_does_not_touch_the_other(self):
        with mock.patch.object(ai_usage.openai_usage, "costs", return_value=[]) as openai_costs, \
                mock.patch.object(ai_usage.anthropic_usage, "costs", side_effect=[AIError("down"), []]) as anthropic_costs:
            ai_usage.summary(KEY)
            with self.assertRaises(AIError):
                ai_usage.summary(ANTHROPIC_KEY, provider="anthropic")
            ai_usage.summary(ANTHROPIC_KEY, provider="anthropic")
            ai_usage.summary(KEY)
        self.assertEqual((openai_costs.call_count, anthropic_costs.call_count), (1, 2))

    def test_the_setting_of_each_admin_key_is_env_only_and_secret(self):
        from src.utils import settings

        for setting in ai_usage.ADMIN_KEYS.values():
            self.assertTrue(settings.REGISTRY[setting].env_only)
            self.assertTrue(settings.REGISTRY[setting].secret)
        self.assertEqual(settings.REGISTRY["ai.anthropic_admin_key"].env, "ANTHROPIC_ADMIN_KEY")


class AnthropicRouteTests(unittest.TestCase):
    def setUp(self):
        ai_usage.clear()
        self.addCleanup(ai_usage.clear)

    def keys(self, **found):
        return mock.patch.object(route.settings, "get", side_effect=lambda name: found.get(name))

    def test_without_the_admin_key_it_says_so_and_whether_anthropic_has_a_key_for_writing(self):
        with self.keys(), mock.patch.object(ai_usage.anthropic_usage, "costs") as costs:
            self.assertEqual(route.get_ai_usage(provider="anthropic"), {"configured": False, "provider": "anthropic", "provider_key": False})
        costs.assert_not_called()
        with self.keys(**{"ai.anthropic.api_key": "sk-ant-api03-x"}):
            self.assertTrue(route.get_ai_usage(provider="anthropic")["provider_key"])

    def test_with_the_key_it_answers_what_anthropic_billed_and_never_asks_openai(self):
        with self.keys(**{"ai.anthropic_admin_key": ANTHROPIC_KEY}), \
                mock.patch.object(ai_usage.anthropic_usage, "costs", return_value=[day("2026-10-01", ("x", 3.0))]), \
                mock.patch.object(ai_usage.openai_usage, "costs") as openai_costs:
            result = route.get_ai_usage(provider="anthropic")
        self.assertEqual((result["configured"], result["provider"], result["total"]), (True, "anthropic", 3.0))
        openai_costs.assert_not_called()

    def test_a_failure_is_a_502_that_never_carries_the_key(self):
        with self.keys(**{"ai.anthropic_admin_key": ANTHROPIC_KEY}), \
                mock.patch.object(ai_usage.anthropic_usage, "costs", side_effect=AIError(f"rechazada {ANTHROPIC_KEY}")), self.assertRaises(HTTPException) as caught:
            route.get_ai_usage(provider="anthropic")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn(ANTHROPIC_KEY, caught.exception.detail)

    def test_only_the_providers_with_an_admin_key_api_can_be_asked(self):
        param = route.get_ai_usage.__defaults__ if route.get_ai_usage.__defaults__ else None
        self.assertIsNotNone(param)
        self.assertEqual(set(ai_usage.ADMIN_KEYS), {"openai", "anthropic"})


class ServerPageTests(unittest.TestCase):
    """The AI spend on the server page: in dollars, never converted, billed by OpenAI when it can be asked and estimated otherwise."""

    TODAY = datetime.date(2026, 11, 12)

    def test_the_months_become_this_month_this_year_and_everything_in_dollars(self):
        months = [{"month": "2026-11", "total": 0.5}, {"month": "2025-12", "total": 4.0}, {"month": "2026-10", "total": 1.25}, {"month": "2026-09", "total": 0}]
        data = ai_usage.rollup(months, self.TODAY)
        self.assertEqual((data["currency"], data["month"], data["year"], data["total"], data["since"]), ("usd", 0.5, 1.75, 5.75, "2025-12"))
        self.assertEqual([m["month"] for m in data["months"]], ["2025-12", "2026-10", "2026-11"])  # a month with no spend is not listed

    def test_with_no_spend_there_is_nothing_and_no_start(self):
        data = ai_usage.rollup([], self.TODAY)
        self.assertEqual((data["month"], data["year"], data["total"], data["since"], data["months"]), (0.0, 0.0, 0.0, None, []))

    def test_lists_of_months_are_added_where_they_share_a_month(self):
        added = ai_usage.add_months([{"month": "2026-10", "total": 1.0}], [{"month": "2026-10", "total": 0.25}, {"month": "2026-11", "total": 0.5}], [])
        self.assertEqual(sorted((m["month"], m["total"]) for m in added), [("2026-10", 1.25), ("2026-11", 0.5)])

    def ask(self, key=KEY, billed=None, estimates=None, error=None, anthropic=None, anthropic_error=None):
        """What the route answers with the bill of OpenAI (`billed`, or failing with `error`), that of Anthropic (`anthropic`, only when
        its admin key is set, or failing with `anthropic_error`) and the app's estimates by provider."""
        from src.routers import server

        keys = {"ai.openai_admin_key": key, "ai.anthropic_admin_key": ANTHROPIC_KEY if (anthropic is not None or anthropic_error) else None}

        def billed_by(admin_key, provider="openai", **_):
            failure = {"openai": error, "anthropic": anthropic_error}[provider]
            if failure:
                raise failure
            return {"months": (billed if provider == "openai" else anthropic) or []}

        errors = error or anthropic_error
        with mock.patch.object(server.settings, "get", side_effect=lambda name: keys[name]), \
                mock.patch.object(server.ai_usage, "summary", side_effect=billed_by), \
                mock.patch.object(server.ai_spend, "group_months_by_provider", return_value=estimates or {}):
            if errors:
                with self.assertLogs(server.logger, "WARNING"):
                    return server.get_ai_costs(db=mock.Mock())
            return server.get_ai_costs(db=mock.Mock())

    def month(self, total):
        from src.routers import server

        return [{"month": server.datetime.date.today().strftime("%Y-%m"), "total": total}]  # the day the route itself sees (the pinned clock)

    def test_with_the_key_openai_is_what_it_billed_and_nothing_else_spent_makes_it_billed(self):
        data = self.ask(billed=self.month(2.0), estimates={"openai": self.month(9.0)})  # the app's estimate of OpenAI is not used
        self.assertEqual((data["source"], data["month"], data["currency"]), ("billed", 2.0, "usd"))
        self.assertEqual(data["providers"], [{"provider": "openai", "source": "billed", "month": 2.0, "year": 2.0, "total": 2.0}])

    def test_the_estimate_of_google_is_added_to_what_openai_billed_and_each_says_how_it_is_known(self):
        data = self.ask(billed=self.month(2.0), estimates={"google": self.month(0.5)})
        self.assertEqual((data["source"], data["month"]), ("mixed", 2.5))
        self.assertEqual([(p["provider"], p["source"], p["month"]) for p in data["providers"]], [("google", "estimated", 0.5), ("openai", "billed", 2.0)])

    def test_a_provider_that_cost_nothing_is_not_listed(self):
        data = self.ask(billed=self.month(2.0), estimates={"google": self.month(0.0)})
        self.assertEqual(([p["provider"] for p in data["providers"]], data["source"]), (["openai"], "billed"))

    def test_without_a_key_everything_is_the_estimate(self):
        data = self.ask(key=None, estimates={"openai": self.month(0.75), "google": self.month(0.25)})
        self.assertEqual((data["source"], data["month"]), ("estimated", 1.0))
        self.assertEqual({p["source"] for p in data["providers"]}, {"estimated"})

    def test_when_openai_fails_its_part_falls_back_to_the_estimate(self):
        data = self.ask(error=AIError("down"), estimates={"openai": self.month(0.75)})
        self.assertEqual((data["source"], data["month"]), ("estimated", 0.75))

    def test_with_the_admin_key_of_anthropic_what_it_billed_replaces_the_estimate_too(self):
        data = self.ask(billed=self.month(2.0), anthropic=self.month(1.5), estimates={"anthropic": self.month(9.0), "google": self.month(0.5)})
        self.assertEqual((data["source"], data["month"]), ("mixed", 4.0))
        self.assertEqual([(p["provider"], p["source"], p["month"]) for p in data["providers"]], [("anthropic", "billed", 1.5), ("google", "estimated", 0.5), ("openai", "billed", 2.0)])

    def test_with_only_the_admin_keys_of_both_and_nothing_else_spent_it_is_all_billed(self):
        data = self.ask(billed=self.month(2.0), anthropic=self.month(1.5))
        self.assertEqual((data["source"], data["month"]), ("billed", 3.5))

    def test_when_anthropic_fails_only_its_part_falls_back_to_the_estimate(self):
        data = self.ask(billed=self.month(2.0), anthropic_error=AIError("down"), estimates={"anthropic": self.month(0.75)})
        self.assertEqual([(p["provider"], p["source"], p["month"]) for p in data["providers"]], [("anthropic", "estimated", 0.75), ("openai", "billed", 2.0)])

    def test_without_the_key_of_anthropic_it_is_not_asked(self):
        from src.routers import server

        with mock.patch.object(server.settings, "get", side_effect=lambda name: KEY if name == "ai.openai_admin_key" else None), \
                mock.patch.object(server.ai_usage, "summary", return_value={"months": []}) as summary, \
                mock.patch.object(server.ai_spend, "group_months_by_provider", return_value={}):
            server.get_ai_costs(db=mock.Mock())
        self.assertEqual([c.kwargs["provider"] for c in summary.call_args_list], ["openai"])


if __name__ == "__main__":
    unittest.main()

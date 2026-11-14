"""The real balance of the accounts behind the group's keys: what OpenRouter's /credits says, how a failure is told, the few minutes
it is remembered and the admin route."""
import unittest
from unittest import mock

import httpx
import openai

from src import auth
from src.clients import provider_balance
from src.clients.ai_error import AIError, ProviderError, QuotaError
from src.routers.manage import ai_usage as route
from src.utils import ai_balances, settings
from tests import ai_env

KEY = "sk-or-v1-FAKE-key-for-tests-0123456789abcdef"


def error(cls, status, body):
    return cls("boom", response=httpx.Response(status, request=httpx.Request("GET", "https://openrouter.ai/api/v1/credits")), body=body)


def client_answering(answer=None, failure=None):
    client = mock.Mock()
    if failure:
        client.get.side_effect = failure
    else:
        client.get.return_value = answer
    return mock.patch.object(provider_balance, "OpenAI", return_value=client)


class OpenRouterBalanceTests(unittest.TestCase):
    def test_it_says_what_was_bought_what_was_used_and_what_is_left(self):
        with client_answering({"data": {"total_credits": 20.5, "total_usage": 7.25}}) as build:
            found = provider_balance.openrouter(KEY)
        self.assertEqual(found, {"credits": 20.5, "usage": 7.25, "remaining": 13.25})
        self.assertEqual(build.call_args.kwargs["base_url"], provider_balance.OPENROUTER_URL)

    def test_an_account_that_bought_nothing_has_nothing_left(self):
        with client_answering({"data": {"total_credits": 0, "total_usage": 0}}):
            self.assertEqual(provider_balance.openrouter(KEY)["remaining"], 0.0)

    def test_a_refused_key_a_quota_and_an_answer_nobody_expected_are_the_apps_errors_and_never_carry_the_key(self):
        cases = (
            (error(openai.AuthenticationError, 401, {"error": {"message": f"bad {KEY}"}}), ProviderError),
            (error(openai.RateLimitError, 429, {"error": {"message": "slow"}}), QuotaError),
            (KeyError("data"), AIError),
        )
        for failure, expected in cases:
            with self.subTest(failure=type(failure).__name__), client_answering(failure=failure), self.assertRaises(expected) as caught:
                provider_balance.openrouter(KEY)
            self.assertIs(type(caught.exception), expected)
            self.assertNotIn(KEY, str(caught.exception))

    def test_a_malformed_answer_is_an_error_and_not_a_crash(self):
        with client_answering({"data": {"total_credits": "x"}}), self.assertRaises(AIError):
            provider_balance.openrouter(KEY)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        ai_balances.clear()
        self.addCleanup(ai_balances.clear)

    def keys(self, **overrides):
        table = {**ai_env.group(None), **overrides}
        return mock.patch.object(settings, "get", side_effect=lambda k: table[k])

    def asking(self, answer):
        return mock.patch.dict(provider_balance.BALANCES, {"openrouter": mock.Mock(side_effect=answer if isinstance(answer, list) else None, return_value=None if isinstance(answer, list) else answer)})

    def test_only_the_providers_that_have_a_key_and_a_balance_to_ask_are_asked(self):
        with self.keys(**{"ai.openai.api_key": "O", "ai.google.api_key": "G"}), self.asking({"credits": 1.0, "usage": 0.0, "remaining": 1.0}) as asked:
            self.assertEqual(ai_balances.summary(), [])
            asked["openrouter"].assert_not_called()
        with self.keys(**{"ai.openrouter.api_key": KEY}), self.asking({"credits": 5.0, "usage": 1.0, "remaining": 4.0}):
            self.assertEqual(ai_balances.summary(), [{"provider": "openrouter", "credits": 5.0, "usage": 1.0, "remaining": 4.0}])

    def test_the_answer_is_kept_a_few_minutes_and_refresh_asks_again(self):
        with self.keys(**{"ai.openrouter.api_key": KEY}), self.asking({"credits": 5.0, "usage": 1.0, "remaining": 4.0}) as asked:
            ai_balances.summary()
            ai_balances.summary()
            self.assertEqual(asked["openrouter"].call_count, 1)
            ai_balances.summary(refresh=True)
            self.assertEqual(asked["openrouter"].call_count, 2)

    def test_a_failure_comes_with_its_error_and_is_not_remembered(self):
        with self.keys(**{"ai.openrouter.api_key": KEY}), self.asking([ProviderError("openrouter: denied", "denied"), {"credits": 5.0, "usage": 1.0, "remaining": 4.0}]):
            self.assertEqual(ai_balances.summary(), [{"provider": "openrouter", "error": "openrouter: denied"}])
            self.assertEqual(ai_balances.summary()[0]["remaining"], 4.0, "the next open asks again")


class RouteTests(unittest.TestCase):
    def test_the_admin_gets_the_balances_and_can_ask_for_fresh_ones(self):
        with mock.patch.object(route.ai_balances, "summary", return_value=[{"provider": "openrouter", "remaining": 3.0}]) as summary:
            body = route.get_ai_balances()
            route.get_ai_balances(refresh=True)
        self.assertEqual(body, {"balances": [{"provider": "openrouter", "remaining": 3.0}]})
        self.assertEqual([c.args[0] for c in summary.call_args_list], [False, True])

    def test_it_is_an_admin_route_of_the_panel(self):
        self.assertTrue(any(d.dependency is auth.require_admin for d in route.router.dependencies))
        self.assertIn("/manage/ai-usage/balances", {r.path for r in route.router.routes})


if __name__ == "__main__":
    unittest.main()

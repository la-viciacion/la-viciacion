"""Anthropic (Claude) as the third provider of the group's key: the client of the notices, how its errors are read, the models of the
chat and the guide and the panel's list of models."""
import os
import types
import unittest
from unittest import mock

import anthropic
import httpx
from fastapi import HTTPException
from pydantic_ai.models.anthropic import AnthropicModel

from src.chat import model as chat_model
from src.clients import anthropic_ai, failure, quota, used
from src.clients.ai_error import AIError, ProviderError, QuotaError
from src.guide import agent as guide_agent
from src.routers.manage import system
from src.utils import ai, ai_providers, settings
from tests import ai_env

KEY = "sk-ant-api03-FAKE-key-for-tests-0123456789"


def api_error(cls, status, body):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request, headers={"retry-after": "7"}), body=body)


def message(text="Hola", usage=None, stop="end_turn"):
    usage = usage or types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)], usage=usage, stop_reason=stop)


class ClientTests(unittest.TestCase):
    def setUp(self):
        anthropic_ai._client.cache_clear()
        used.discard()

    def generate(self, reply, temperature=0.5):
        client = mock.Mock()
        client.messages.create.return_value = reply
        with mock.patch.object(anthropic_ai, "_client", return_value=client):
            return client, anthropic_ai.generate(KEY, "claude-haiku-5-5", "sys", "usr", temperature)

    def test_it_asks_with_the_system_prompt_apart_and_returns_the_text(self):
        client, text = self.generate(message(" Hola "))
        self.assertEqual(text, "Hola")
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual((kwargs["model"], kwargs["system"], kwargs["messages"]), ("claude-haiku-5-5", "sys", [{"role": "user", "content": "usr"}]))
        self.assertEqual(kwargs["max_tokens"], anthropic_ai.MAX_TOKENS)

    def test_a_temperature_above_what_anthropic_accepts_is_lowered(self):
        client, _ = self.generate(message(), temperature=1.8)
        self.assertEqual(client.messages.create.call_args.kwargs["temperature"], 1.0)

    def test_the_tokens_are_left_with_the_cache_inside_the_input(self):
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=100, cache_creation_input_tokens=20)
        self.generate(message(usage=usage))
        self.assertEqual(used.take(), used.Used(input_tokens=130, cached_tokens=100, output_tokens=5))

    def test_an_answer_with_no_text_is_an_error_that_says_why(self):
        with self.assertRaises(AIError) as caught:
            self.generate(message("", stop="max_tokens"))
        self.assertIn("max_tokens", str(caught.exception))

    def test_the_client_is_cached_by_key_with_a_timeout(self):
        with mock.patch.object(anthropic_ai.anthropic, "Anthropic") as build:
            first, second = anthropic_ai._client(KEY), anthropic_ai._client(KEY)
        self.assertIs(first, second)
        build.assert_called_once_with(api_key=KEY, timeout=anthropic_ai.TIMEOUT_SECONDS)


class ListModelsTests(unittest.TestCase):
    def listing(self, ids=None, error=None):
        client = mock.Mock()
        if error:
            client.models.list.side_effect = error
        else:
            client.models.list.return_value = [types.SimpleNamespace(id=i) for i in ids]
        return mock.patch.object(anthropic_ai.anthropic, "Anthropic", return_value=client)

    def test_it_lists_the_claude_models_sorted(self):
        with self.listing(["claude-sonnet-5-5", "claude-haiku-5-5", "other"]):
            self.assertEqual(anthropic_ai.list_models(KEY), ["claude-haiku-5-5", "claude-sonnet-5-5"])

    def test_a_refused_key_is_a_provider_error_that_never_carries_the_key(self):
        error = api_error(anthropic.AuthenticationError, 401, {"error": {"message": f"bad key {KEY}"}})
        with self.listing(error=error), self.assertRaises(ProviderError) as caught:
            anthropic_ai.list_models(KEY)
        self.assertEqual(caught.exception.kind, failure.DENIED)
        self.assertNotIn(KEY, str(caught.exception))

    def test_a_rate_limit_is_a_quota_error(self):
        error = api_error(anthropic.RateLimitError, 429, {"error": {"type": "rate_limit_error", "message": "slow down"}})
        with self.listing(error=error), self.assertRaises(QuotaError) as caught:
            anthropic_ai.list_models(KEY)
        self.assertEqual(caught.exception.quota.retry_after, 7)


class QuotaReadingTests(unittest.TestCase):
    def test_a_429_of_anthropic_is_a_quota_with_its_wait(self):
        found = quota.classify(api_error(anthropic.RateLimitError, 429, {"error": {"type": "rate_limit_error", "message": "slow"}}))
        self.assertEqual((found.kind, found.retry_after, found.message), ("unknown", 7, "slow"))

    def test_an_account_without_balance_is_billing_even_though_anthropic_answers_400(self):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}
        found = quota.classify(api_error(anthropic.BadRequestError, 400, body))
        self.assertEqual(found.kind, "billing")

    def test_another_bad_request_is_not_a_quota(self):
        self.assertIsNone(quota.classify(api_error(anthropic.BadRequestError, 400, {"error": {"message": "max_tokens too big"}})))

    def test_an_overloaded_anthropic_is_told_as_overloaded(self):
        self.assertEqual(failure.kind(api_error(anthropic.APIStatusError, 529, {"error": {"type": "overloaded_error"}})), failure.OVERLOADED)


class WiringTests(unittest.TestCase):
    def test_anthropic_is_a_provider_with_its_own_variables(self):
        self.assertIn("anthropic", settings.AI_PROVIDERS)
        env = {"ANTHROPIC_AI_API_KEY": KEY, "ANTHROPIC_AI_MODEL": "claude-haiku-5-5", "ANTHROPIC_CHAT_AI_MODEL": "claude-sonnet-5-5"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(settings.get("ai.anthropic.api_key"), KEY)
            self.assertEqual(settings.get("ai.anthropic.model"), "claude-haiku-5-5")
            self.assertEqual(settings.get("ai.anthropic.chat_model"), "claude-sonnet-5-5")
        self.assertTrue(settings.REGISTRY["ai.anthropic.api_key"].env_only)  # never stored

    def test_the_notices_the_chat_and_the_guide_can_run_on_it(self):
        self.assertIs(ai.PROVIDERS["anthropic"], anthropic_ai.generate)
        for builders in (chat_model.BUILDERS, guide_agent.BUILDERS):
            self.assertIsInstance(builders["anthropic"]("claude-haiku-5-5", KEY), AnthropicModel)

    def test_with_only_its_key_set_it_is_the_provider_in_use(self):
        table = ai_env.group("anthropic", KEY, "claude-haiku-5-5")
        with mock.patch.object(settings, "get", side_effect=lambda k: table.get(k, settings.REGISTRY[k].default)):
            self.assertEqual(ai_providers.available(), ["anthropic"])
            self.assertEqual(ai_providers.group_credentials(), ("anthropic", KEY, "claude-haiku-5-5"))

    def test_the_panel_lists_its_models_with_the_group_key(self):
        with mock.patch.object(system.ai_providers, "api_key", return_value=KEY), \
             mock.patch.dict(system.LISTERS, {"anthropic": lambda key: ["claude-haiku-5-5"]}):
            body = system.list_ai_models("anthropic", admin=types.SimpleNamespace(username="root"))
        self.assertEqual((body["provider"], body["models"]), ("anthropic", ["claude-haiku-5-5"]))

    def test_the_panel_says_which_variable_is_missing(self):
        with mock.patch.object(system.ai_providers, "api_key", return_value=None), self.assertRaises(HTTPException) as caught:
            system.list_ai_models("anthropic", admin=types.SimpleNamespace(username="root"))
        self.assertIn("ANTHROPIC_AI_API_KEY", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

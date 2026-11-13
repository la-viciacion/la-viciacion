"""OpenRouter as the fourth provider of the group's key: its client (OpenAI's, on OpenRouter's address), how its 402 is read, the model
names it needs (provider/model) and the wiring of the notices, the chat and the guide."""
import os
import types
import unittest
from unittest import mock

import httpx
import openai
from pydantic_ai.models.openrouter import OpenRouterModel

from src.chat import model as chat_model
from src.clients import openrouter_ai, quota, used
from src.clients.ai_error import AIError, ProviderError, QuotaError
from src.guide import agent as guide_agent
from src.utils import ai, ai_cost, ai_providers, settings
from tests import ai_env

KEY = "sk-or-v1-FAKE-key-for-tests-0123456789abcdef"


def api_error(cls, status, body):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=request), body=body)


def completion(text="Hola"):
    usage = types.SimpleNamespace(prompt_tokens=12, completion_tokens=4, prompt_tokens_details=None, completion_tokens_details=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))], usage=usage)


class ClientTests(unittest.TestCase):
    def setUp(self):
        openrouter_ai._client.cache_clear()
        used.discard()

    def test_it_asks_openrouters_address_with_the_official_client_and_caches_it_by_key(self):
        with mock.patch.object(openrouter_ai, "OpenAI") as build:
            first, second = openrouter_ai._client(KEY), openrouter_ai._client(KEY)
        self.assertIs(first, second)
        build.assert_called_once_with(api_key=KEY, base_url="https://openrouter.ai/api/v1", timeout=openrouter_ai.TIMEOUT_SECONDS)

    def test_it_returns_the_text_and_leaves_the_tokens(self):
        client = mock.Mock()
        client.chat.completions.create.return_value = completion(" Hola ")
        with mock.patch.object(openrouter_ai, "_client", return_value=client):
            text = openrouter_ai.generate(KEY, "anthropic/claude-haiku-5-5", "sys", "usr", 0.5)
        self.assertEqual(text, "Hola")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual((kwargs["model"], kwargs["messages"][0]["role"]), ("anthropic/claude-haiku-5-5", "system"))
        self.assertEqual(used.take(), used.Used(input_tokens=12, output_tokens=4))

    def test_an_answer_with_no_text_is_an_error(self):
        client = mock.Mock()
        client.chat.completions.create.return_value = completion("")
        with mock.patch.object(openrouter_ai, "_client", return_value=client), self.assertRaises(AIError):
            openrouter_ai.generate(KEY, "m/x", "sys", "usr", 0.5)

    def listing(self, ids=None, error=None):
        client = mock.Mock()
        if error:
            client.models.list.side_effect = error
        else:
            client.models.list.return_value = [types.SimpleNamespace(id=i) for i in ids]
        return mock.patch.object(openrouter_ai, "OpenAI", return_value=client)

    def test_it_lists_the_models_sorted(self):
        with self.listing(["openai/gpt-4.1-mini", "anthropic/claude-haiku-5-5"]):
            self.assertEqual(openrouter_ai.list_models(KEY), ["anthropic/claude-haiku-5-5", "openai/gpt-4.1-mini"])

    def test_a_failure_while_listing_never_carries_the_key(self):
        error = api_error(openai.AuthenticationError, 401, {"error": {"message": f"bad {KEY}"}})
        with self.listing(error=error), self.assertRaises(ProviderError) as caught:
            openrouter_ai.list_models(KEY)
        self.assertNotIn(KEY, str(caught.exception))

    def test_no_credit_while_listing_is_a_billing_quota(self):
        with self.listing(error=api_error(openai.APIStatusError, 402, {"error": {"message": "Insufficient credits"}})), self.assertRaises(QuotaError) as caught:
            openrouter_ai.list_models(KEY)
        self.assertEqual(caught.exception.quota.kind, "billing")


class QuotaReadingTests(unittest.TestCase):
    def test_an_account_without_credit_answers_402_and_it_is_billing(self):
        found = quota.classify(api_error(openai.APIStatusError, 402, {"error": {"message": "Insufficient credits. Add more using https://openrouter.ai/settings/credits"}}))
        self.assertEqual(found.kind, "billing")
        self.assertIn("Insufficient credits", found.message)

    def test_a_rate_limit_is_still_a_429_quota(self):
        self.assertIsNotNone(quota.classify(api_error(openai.RateLimitError, 429, {"error": {"message": "slow"}})))


class WiringTests(unittest.TestCase):
    def test_it_is_a_provider_with_its_own_environment_variables(self):
        self.assertIn("openrouter", settings.AI_PROVIDERS)
        env = {"OPENROUTER_AI_API_KEY": KEY, "OPENROUTER_AI_MODEL": "openai/gpt-4.1-mini", "OPENROUTER_CHAT_AI_MODEL": "anthropic/claude-sonnet-5-5"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(settings.get("ai.openrouter.api_key"), KEY)
            self.assertEqual(settings.get("ai.openrouter.model"), "openai/gpt-4.1-mini")
            self.assertEqual(settings.get("ai.openrouter.chat_model"), "anthropic/claude-sonnet-5-5")
        self.assertTrue(settings.REGISTRY["ai.openrouter.api_key"].env_only)

    def test_a_model_named_provider_slash_model_is_valid_in_every_pick(self):
        for key in ("ai.model.openrouter", "chat.model.openrouter", "guide.model.openrouter"):
            self.assertIsNone(settings.REGISTRY[key].check("meta-llama/llama-3.3-70b-instruct:free"))
        self.assertIsNotNone(settings.REGISTRY["ai.model.openrouter"].check("bad name"))
        self.assertIsNotNone(settings.REGISTRY["ai.model.openrouter"].check("/x"))

    def test_the_notices_the_chat_and_the_guide_can_run_on_it(self):
        self.assertIs(ai.PROVIDERS["openrouter"], openrouter_ai.generate)
        for builders in (chat_model.BUILDERS, guide_agent.BUILDERS):
            self.assertIsInstance(builders["openrouter"]("anthropic/claude-haiku-5-5", KEY), OpenRouterModel)

    def test_with_only_its_key_it_is_the_provider_in_use(self):
        table = ai_env.group("openrouter", KEY, "openai/gpt-4.1-mini")
        with mock.patch.object(settings, "get", side_effect=lambda k: table.get(k, settings.REGISTRY[k].default)):
            self.assertEqual(ai_providers.group_credentials(), ("openrouter", KEY, "openai/gpt-4.1-mini"))

    def test_its_models_are_priced_by_the_same_list_as_the_others(self):
        used_ = used.Used(input_tokens=1_000_000, output_tokens=0)
        self.assertGreater(ai_cost.completion_cost_micros("openrouter", "openai/gpt-4.1-mini", used_) or 0, 0)


if __name__ == "__main__":
    unittest.main()

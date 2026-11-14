"""The four providers of the group's key (OpenAI, Google, Anthropic, OpenRouter): how each one's model is built, the variables each has,
the models each lists and how each one's way of saying "no" (a refused key, a rate limit, no balance) is read."""
import os
import types
import unittest
from pathlib import Path
from unittest import mock

import anthropic
import httpx
import openai
from fastapi import HTTPException
from google.genai import errors as google_errors
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.native_tools import WebSearchTool

from src.clients import failure, model_list, quota
from src.clients.ai_error import AIError, ProviderError, QuotaError
from src.routers.manage import system
from src.utils import ai_build, ai_providers, ai_source, settings
from tests import ai_env

KEY = "sk-FAKE-key-for-tests-0123456789"


def http_error(cls, status, body, url="https://example.test/v1"):
    return cls("boom", response=httpx.Response(status, request=httpx.Request("POST", url)), body=body)


class DocumentedTests(unittest.TestCase):
    """A provider is not finished until a person can find how to set it up: the .env template, the variables page and the rule of
    AGENTS.md that lists the keys that never go in the database."""

    ROOT = Path(__file__).resolve().parents[2]

    def test_every_provider_has_its_variables_in_the_template_and_the_docs(self):
        template = (self.ROOT / ".env.template").read_text(encoding="utf-8")
        docs = (self.ROOT / "docs" / "configuracion" / "variables.md").read_text(encoding="utf-8")
        for provider in settings.AI_PROVIDERS:
            for name in ("AI_API_KEY", "AI_MODEL", "CHAT_AI_MODEL"):
                variable = f"{provider.upper()}_{name}"
                with self.subTest(variable=variable):
                    self.assertIn(variable, template)
                    self.assertIn(variable, docs)

    def test_the_admin_keys_are_in_the_template_the_docs_and_the_rule_too(self):
        template = (self.ROOT / ".env.template").read_text(encoding="utf-8")
        docs = (self.ROOT / "docs" / "configuracion" / "variables.md").read_text(encoding="utf-8")
        rules = (self.ROOT / "AGENTS.md").read_text(encoding="utf-8")
        from src.utils import ai_usage

        for setting in ai_usage.ADMIN_KEYS.values():
            variable = settings.REGISTRY[setting].env
            with self.subTest(variable=variable):
                for text in (template, docs, rules):
                    self.assertIn(variable, text)

    def test_the_keys_are_in_the_rule_that_says_they_never_go_in_the_database(self):
        rules = (self.ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for provider in settings.AI_PROVIDERS:
            self.assertIn(f"{provider.upper()}_AI_API_KEY", rules)


class ModelProblemTests(unittest.TestCase):
    def test_an_openrouter_model_without_its_vendor_is_said_with_the_fix(self):
        found = ai_providers.model_problem("openrouter", "gpt-4o-mini")
        self.assertIn("openai/gpt-4o-mini", found)
        self.assertIn("proveedor/modelo", found)

    def test_a_valid_name_missing_values_and_other_providers_have_no_problem(self):
        self.assertIsNone(ai_providers.model_problem("openrouter", "openai/gpt-4o-mini"))
        self.assertIsNone(ai_providers.model_problem("openrouter", "~anthropic/claude-haiku-latest"))
        self.assertIsNone(ai_providers.model_problem("openrouter", None))
        self.assertIsNone(ai_providers.model_problem("openai", "gpt-4o-mini"))
        self.assertIsNone(ai_providers.model_problem(None, None))

    def test_what_a_use_runs_on_carries_the_problem_to_the_panel(self):
        table = ai_env.group("openrouter", KEY, "gpt-4o-mini")
        with mock.patch.object(settings, "get", side_effect=lambda k: table[k]):
            for use in ai_providers.USES:
                self.assertIn("openai/gpt-4o-mini", ai_providers.in_use(use)["problem"])
        table = ai_env.group("openrouter", KEY, "openai/gpt-4o-mini")
        with mock.patch.object(settings, "get", side_effect=lambda k: table[k]):
            self.assertIsNone(ai_providers.in_use(ai_providers.CHAT)["problem"])


class BuildTests(unittest.TestCase):
    def test_every_provider_of_the_settings_has_its_model(self):
        self.assertEqual(set(ai_build._CLASSES), set(settings.AI_PROVIDERS))
        self.assertEqual(set(model_list.LISTERS), set(settings.AI_PROVIDERS))

    def test_each_provider_builds_its_own_kind_of_model_with_the_name_it_was_given(self):
        expected = {"openai": OpenAIChatModel, "google": GoogleModel, "anthropic": AnthropicModel, "openrouter": OpenRouterModel}
        for provider, model_class in expected.items():
            with self.subTest(provider=provider):
                built = ai_build.build(provider, "vendor/some-model", KEY)
                self.assertIsInstance(built, model_class)
                self.assertEqual(built.model_name, "vendor/some-model")

    def test_openai_needs_its_responses_api_to_search_the_web_and_nobody_else_changes(self):
        self.assertIsInstance(ai_build.build("openai", "gpt-x", KEY, web_search=True), OpenAIResponsesModel)
        for provider in ("google", "anthropic", "openrouter"):
            self.assertIs(type(ai_build.build(provider, "v/m", KEY, web_search=True)), type(ai_build.build(provider, "v/m", KEY)))

    def test_the_guides_web_search_fits_the_model_of_every_provider(self):
        for provider in settings.AI_PROVIDERS:
            with self.subTest(provider=provider):
                built = ai_build.build(provider, "vendor/some-model", KEY, web_search=True)
                self.assertIn(WebSearchTool, built.supported_native_tools())

    def test_an_unknown_provider_is_not_built(self):
        with self.assertRaises(KeyError):
            ai_build.build("nobody", "m", KEY)

    def test_the_model_of_a_use_is_the_one_the_admin_chose_for_it_and_the_guide_gets_the_one_that_searches(self):
        table = ai_env.group("openai", KEY, "gpt-notices", **{"chat.model.openai": "gpt-chat", "guide.model.openai": "gpt-guide"})
        with mock.patch.object(settings, "get", side_effect=lambda k: table[k]):
            self.assertIs(type(ai_build.model_for(ai_providers.CHAT)), OpenAIChatModel)
            self.assertEqual(ai_build.model_for(ai_providers.CHAT).model_name, "gpt-chat")
            self.assertIs(type(ai_build.model_for(ai_providers.GUIDE)), OpenAIResponsesModel)
            self.assertEqual(ai_build.model_for(ai_providers.GUIDE).model_name, "gpt-guide")

    def test_a_players_own_source_wins_over_the_groups(self):
        source = ai_source.Source("user", "anthropic", KEY, "claude-haiku-5-5")
        table = ai_env.group("openai", "GROUPKEY", "gpt-x")
        with mock.patch.object(settings, "get", side_effect=lambda k: table[k]):
            built = ai_build.model_for(ai_providers.CHAT, source)
        self.assertIsInstance(built, AnthropicModel)
        self.assertEqual(built.model_name, "claude-haiku-5-5")


class VariablesTests(unittest.TestCase):
    def test_every_provider_has_its_key_and_models_in_the_environment_and_never_in_the_database(self):
        for provider in settings.AI_PROVIDERS:
            prefix = provider.upper()
            env = {f"{prefix}_AI_API_KEY": KEY, f"{prefix}_AI_MODEL": "notices-model", f"{prefix}_CHAT_AI_MODEL": "chat-model"}
            with self.subTest(provider=provider), mock.patch.dict(os.environ, env):
                self.assertEqual(settings.get(f"ai.{provider}.api_key"), KEY)
                self.assertEqual(settings.get(f"ai.{provider}.model"), "notices-model")
                self.assertEqual(settings.get(f"ai.{provider}.chat_model"), "chat-model")
                self.assertTrue(settings.REGISTRY[f"ai.{provider}.api_key"].env_only)

    def test_with_only_one_key_that_provider_is_the_one_in_use(self):
        for provider in settings.AI_PROVIDERS:
            table = ai_env.group(provider, KEY, "m")
            with self.subTest(provider=provider), mock.patch.object(settings, "get", side_effect=lambda k, t=table: t[k]):
                self.assertEqual(ai_providers.available(), [provider])
                self.assertEqual(ai_providers.group_credentials(), (provider, KEY, "m"))

    def test_a_model_named_provider_slash_model_is_valid_in_every_pick(self):
        for key in ("ai.model.openrouter", "chat.model.openrouter", "guide.model.openrouter"):
            self.assertIsNone(settings.REGISTRY[key].check("meta-llama/llama-3.3-70b-instruct:free"))
        self.assertIsNone(settings.REGISTRY["ai.model.openrouter"].check("~anthropic/claude-haiku-latest"))
        self.assertIsNotNone(settings.REGISTRY["ai.model.openrouter"].check("bad name"))
        self.assertIsNotNone(settings.REGISTRY["ai.model.openrouter"].check("/x"))


class ModelListTests(unittest.TestCase):
    def test_openai_lists_its_models_sorted(self):
        client = mock.Mock()
        client.models.list.return_value = [types.SimpleNamespace(id="gpt-5"), types.SimpleNamespace(id="gpt-4.1")]
        with mock.patch.object(model_list, "OpenAI", return_value=client) as build:
            self.assertEqual(model_list.list_models("openai", KEY), ["gpt-4.1", "gpt-5"])
        self.assertNotIn("base_url", build.call_args.kwargs)

    @staticmethod
    def catalogue(*entries):
        """What OpenRouter's /models answers: id, what the model reads and writes and what it supports."""
        return {"data": [{"id": i, "architecture": {"output_modalities": out}, "supported_parameters": params} for i, out, params in entries]}

    def test_openrouter_proves_the_key_with_its_own_endpoint_and_offers_only_models_that_write_text_with_tools(self):
        client = mock.Mock()
        client.get.side_effect = lambda path, cast_to: {"/key": {"data": {}}, "/models": self.catalogue(
            ("openai/gpt-4.1-mini", ["text"], ["tools", "temperature"]),
            ("anthropic/claude-haiku-5-5", ["text"], ["tools"]),
            ("black-forest-labs/flux", ["image"], ["tools"]),
            ("vendor/no-tools", ["text"], ["temperature"]),
            ("~openai/gpt-latest", ["text"], ["tools"]),
        )}[path]
        with mock.patch.object(model_list, "OpenAI", return_value=client) as build:
            self.assertEqual(model_list.list_models("openrouter", KEY), ["anthropic/claude-haiku-5-5", "openai/gpt-4.1-mini", "~openai/gpt-latest"])
        self.assertEqual(build.call_args.kwargs["base_url"], model_list.OPENROUTER_URL)
        self.assertEqual([c.args[0] for c in client.get.call_args_list], ["/key", "/models"])

    def test_a_wrong_openrouter_key_is_refused_before_the_catalogue_is_read(self):
        client = mock.Mock()
        client.get.side_effect = http_error(openai.AuthenticationError, 401, {"error": {"message": "No auth credentials found"}})
        with mock.patch.object(model_list, "OpenAI", return_value=client), self.assertRaises(ProviderError) as caught:
            model_list.list_models("openrouter", KEY)
        self.assertEqual(caught.exception.kind, failure.DENIED)
        client.get.assert_called_once()

    def test_anthropic_lists_only_its_claude_models(self):
        client = mock.Mock()
        client.models.list.return_value = [types.SimpleNamespace(id="claude-sonnet-5-5"), types.SimpleNamespace(id="other"), types.SimpleNamespace(id="claude-haiku-5-5")]
        with mock.patch.object(model_list.anthropic, "Anthropic", return_value=client):
            self.assertEqual(model_list.list_models("anthropic", KEY), ["claude-haiku-5-5", "claude-sonnet-5-5"])

    def test_google_lists_the_gemini_models_that_write_text_without_their_prefix(self):
        def model(name, actions):
            return types.SimpleNamespace(name=name, supported_actions=actions)

        client = mock.Mock()
        client.models.list.return_value = [
            model("models/gemini-2.5-flash", ["generateContent"]), model("models/gemini-embedding", ["embedContent"]),
            model("models/imagen-4", ["generateContent"]), model(None, ["generateContent"]),
        ]
        with mock.patch.object(model_list.genai, "Client", return_value=client):
            self.assertEqual(model_list.list_models("google", KEY), ["gemini-2.5-flash"])

    def test_a_refused_key_is_a_provider_error_that_never_carries_the_key(self):
        error = http_error(openai.AuthenticationError, 401, {"error": {"message": f"bad {KEY}"}})
        client = mock.Mock()
        client.models.list.side_effect = error
        with mock.patch.object(model_list, "OpenAI", return_value=client), self.assertRaises(ProviderError) as caught:
            model_list.list_models("openai", KEY)
        self.assertEqual(caught.exception.kind, failure.DENIED)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertTrue(str(caught.exception).startswith("openai:"))

    def test_a_rate_limit_and_no_balance_are_quota_errors_and_anything_else_a_plain_one(self):
        cases = (
            (http_error(openai.RateLimitError, 429, {"error": {"message": "slow"}}), QuotaError),
            (http_error(openai.APIStatusError, 402, {"error": {"message": "Insufficient credits"}}), QuotaError),
            (RuntimeError("boom"), AIError),
        )
        for error, expected in cases:
            client = mock.Mock()
            client.get.side_effect = error
            with self.subTest(error=type(error).__name__), mock.patch.object(model_list, "OpenAI", return_value=client), self.assertRaises(expected) as caught:
                model_list.list_models("openrouter", KEY)
            self.assertIs(type(caught.exception), expected)


class PanelListTests(unittest.TestCase):
    admin = types.SimpleNamespace(username="root")

    def test_the_panel_asks_every_provider_through_the_same_function(self):
        for provider in settings.AI_PROVIDERS:
            with self.subTest(provider=provider), mock.patch.object(system.ai_providers, "api_key", return_value=KEY), \
                    mock.patch.object(system.model_list, "list_models", return_value=["gpt-a"]) as listed:
                body = system.list_ai_models(provider, admin=self.admin)
            listed.assert_called_once_with(provider, KEY)
            self.assertEqual((body["provider"], body["models"]), (provider, ["gpt-a"]))

    def test_without_the_key_it_says_which_variable_is_missing(self):
        with mock.patch.object(system.ai_providers, "api_key", return_value=None), self.assertRaises(HTTPException) as caught:
            system.list_ai_models("anthropic", admin=self.admin)
        self.assertIn("ANTHROPIC_AI_API_KEY", caught.exception.detail)


class ErrorReadingTests(unittest.TestCase):
    def test_a_429_of_anthropic_is_a_quota_with_its_wait(self):
        error = http_error(anthropic.RateLimitError, 429, {"error": {"type": "rate_limit_error", "message": "slow"}})
        error.response.headers["retry-after"] = "7"
        found = quota.classify(error)
        self.assertEqual((found.kind, found.retry_after, found.message), ("unknown", 7, "slow"))

    def test_an_account_without_balance_is_billing_whatever_the_status_the_provider_uses(self):
        anthropic_400 = http_error(anthropic.BadRequestError, 400, {"error": {"message": "Your credit balance is too low to access the Anthropic API."}})
        openrouter_402 = http_error(openai.APIStatusError, 402, {"error": {"message": "Insufficient credits. Add more at openrouter.ai"}})
        for error in (anthropic_400, openrouter_402):
            self.assertEqual(quota.classify(error).kind, "billing")

    def test_another_bad_request_is_not_a_quota(self):
        self.assertIsNone(quota.classify(http_error(anthropic.BadRequestError, 400, {"error": {"message": "max_tokens too big"}})))

    def test_an_overloaded_anthropic_is_told_as_overloaded_and_a_refused_key_as_denied(self):
        self.assertEqual(failure.kind(http_error(anthropic.APIStatusError, 529, {"error": {"type": "overloaded_error"}})), failure.OVERLOADED)
        self.assertEqual(failure.kind(http_error(anthropic.AuthenticationError, 401, {"error": {"message": "x"}})), failure.DENIED)

    def test_googles_429_is_still_read(self):
        error = google_errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
        self.assertIsNotNone(quota.classify(error))


if __name__ == "__main__":
    unittest.main()

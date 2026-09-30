import os
import unittest
from unittest import mock

from fastapi import HTTPException
from google.genai import errors, types

from src.clients import google_ai
from src.clients.ai_error import AIError
from src.database import models
from src.routers import manage
from src.utils import ai, ai_prompts, my_utils, settings
from tests.sqlite_db import make_session

KEY = "AIzaSyFAKE-key-for-tests-0123456789"
OTHER_KEY = "AIzaSyNEWKEY-0123456789-abcdef"


def values(**overrides):
    base = {"ai.enabled": True, "ai.provider": "google", "ai.api_key": KEY, "ai.model": None}
    return mock.patch.object(ai.settings, "get", side_effect=lambda k: {**base, **overrides}[k])


class SettingsTests(unittest.TestCase):
    def test_provider_is_one_of_the_known_ones(self):
        self.assertEqual(settings.coerce("ai.provider", " openai "), "openai")
        with self.assertRaises(ValueError):
            settings.coerce("ai.provider", "claude")

    def test_model_may_be_blank_to_use_the_default_but_not_odd(self):
        self.assertEqual(settings.coerce("ai.model", ""), "")
        self.assertEqual(settings.coerce("ai.model", "gemini-2.5-flash"), "gemini-2.5-flash")
        with self.assertRaises(ValueError):
            settings.coerce("ai.model", "models/x?key=1")

    def test_the_key_is_encrypted_and_never_shown(self):
        self.assertNotIn(KEY, settings._encode("ai.api_key", KEY))
        db = make_session()
        settings.set_values(db, {"ai.api_key": KEY})
        shown = settings.public_view(db)["ai.api_key"]
        self.assertEqual(shown, {"is_set": True, "hint": "…" + KEY[-4:]})


class SeedingTests(unittest.TestCase):
    NAMES = ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL")

    def seed(self, env, db=None):
        db = db or make_session()
        clean = {k: v for k, v in os.environ.items() if k not in self.NAMES}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            settings.seed_from_env(db)
        stored = settings.get_all(db)
        return db, {k: stored[k] for k in ("ai.enabled", "ai.provider", "ai.api_key", "ai.model")}

    def test_ai_variables_seed_the_settings(self):
        _, got = self.seed({"AI_PROVIDER": "google", "AI_API_KEY": KEY, "AI_MODEL": "gemini-2.5-pro"})
        self.assertEqual(got, {"ai.enabled": True, "ai.provider": "google", "ai.api_key": KEY, "ai.model": "gemini-2.5-pro"})

    def test_the_old_openai_variables_keep_an_existing_installation_working(self):
        _, got = self.seed({"OPENAI_API_KEY": "sk-old", "OPENAI_MODEL": "gpt-4o-mini"})
        self.assertEqual((got["ai.provider"], got["ai.api_key"], got["ai.model"]), ("openai", "sk-old", "gpt-4o-mini"))
        self.assertTrue(got["ai.enabled"])

    def test_ai_variables_win_over_the_old_ones(self):
        _, got = self.seed({"AI_API_KEY": KEY, "OPENAI_API_KEY": "sk-old"})
        self.assertEqual((got["ai.provider"], got["ai.api_key"]), ("google", KEY))

    def test_nothing_in_the_environment_seeds_nothing(self):
        db, got = self.seed({})
        self.assertIsNone(got["ai.api_key"])
        self.assertEqual(db.query(models.AppSetting).filter(models.AppSetting.key.like("ai.%")).count(), 0)

    def test_the_database_is_the_source_of_truth_after_the_first_time(self):
        db, _ = self.seed({"AI_API_KEY": KEY})
        settings.set_values(db, {"ai.api_key": OTHER_KEY})
        _, got = self.seed({"AI_API_KEY": KEY, "OPENAI_API_KEY": "sk-old"}, db)
        self.assertEqual((got["ai.provider"], got["ai.api_key"]), ("google", OTHER_KEY))


class CompleteTests(unittest.TestCase):
    def test_off_or_without_a_key_it_answers_nothing_and_calls_nobody(self):
        provider = mock.Mock()
        with mock.patch.dict(ai.PROVIDERS, {"google": provider}):
            with values(**{"ai.enabled": False}):
                self.assertIsNone(ai.complete("s", "u"))
                self.assertFalse(ai.is_ready())
            with values(**{"ai.api_key": None}):
                self.assertIsNone(ai.complete("s", "u"))
                self.assertIsNone(ai.complete("s", "u", force=True))
        provider.assert_not_called()

    def test_force_ignores_the_switch(self):
        provider = mock.Mock(return_value="hola")
        with mock.patch.dict(ai.PROVIDERS, {"google": provider}), values(**{"ai.enabled": False}):
            self.assertEqual(ai.complete("s", "u", force=True), "hola")

    def test_the_provider_model_and_key_come_from_the_settings(self):
        google, openai = mock.Mock(return_value="g"), mock.Mock(return_value="o")
        with mock.patch.dict(ai.PROVIDERS, {"google": google, "openai": openai}):
            with values():
                self.assertEqual(ai.complete("sys", "usr"), "g")
            google.assert_called_once_with(KEY, "gemini-2.5-flash", "sys", "usr", 1.0)  # the provider's default model
            with values(**{"ai.provider": "openai", "ai.model": "gpt-x"}):
                self.assertEqual(ai.complete("sys", "usr"), "o")
            openai.assert_called_once_with(KEY, "gpt-x", "sys", "usr", 1.0)

    def test_a_failure_never_quotes_the_key(self):
        boom = mock.Mock(side_effect=RuntimeError(f"bad key {KEY}"))
        with mock.patch.dict(ai.PROVIDERS, {"google": boom}), values():
            with self.assertRaises(AIError) as caught:
                ai.complete("s", "u")
        self.assertNotIn(KEY, str(caught.exception))


def answer(*texts, finish_reason=None):
    parts = [types.Part(text=t) for t in texts]
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=parts), finish_reason=finish_reason)]
    )


class GoogleClientTests(unittest.TestCase):
    def setUp(self):
        google_ai._client.cache_clear()

    def call(self, reply=None, error=None):
        client = mock.Mock()
        client.models.generate_content.side_effect = error
        client.models.generate_content.return_value = reply
        with mock.patch.object(google_ai, "_client", return_value=client):
            try:
                return client, google_ai.generate(KEY, "gemini-2.5-flash", "sys", "usr", 0.5)
            except AIError as e:
                return client, e

    def test_the_request_carries_the_model_the_prompts_and_the_temperature(self):
        client, text = self.call(answer("hi"))
        self.assertEqual(text, "hi")
        kwargs = client.models.generate_content.call_args.kwargs
        self.assertEqual((kwargs["model"], kwargs["contents"]), ("gemini-2.5-flash", "usr"))
        self.assertEqual((kwargs["config"].system_instruction, kwargs["config"].temperature), ("sys", 0.5))

    def test_the_client_is_built_with_the_key_and_a_timeout_and_reused(self):
        with mock.patch.object(google_ai.genai, "Client") as build:
            first, second = google_ai._client(KEY), google_ai._client(KEY)
        build.assert_called_once()
        self.assertEqual(build.call_args.kwargs["api_key"], KEY)
        self.assertEqual(build.call_args.kwargs["http_options"].timeout, google_ai.TIMEOUT_MS)
        self.assertIs(first, second)

    def test_the_parts_of_the_answer_are_joined(self):
        _, text = self.call(answer("Hola ", "mundo"))
        self.assertEqual(text, "Hola mundo")

    def test_an_error_from_google_says_why_and_not_the_key(self):
        error = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT"}})
        _, got = self.call(error=error)
        self.assertIsInstance(got, AIError)
        self.assertIn("400", str(got))
        self.assertIn("API key not valid", str(got))
        self.assertNotIn(KEY, str(got))

    def test_a_blocked_prompt_is_explained(self):
        blocked = types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason=types.BlockedReason.SAFETY)
        )
        _, got = self.call(blocked)
        self.assertIn("SAFETY", str(got))

    def test_an_answer_without_text_says_how_it_ended(self):
        _, got = self.call(answer(finish_reason=types.FinishReason.MAX_TOKENS))
        self.assertIn("MAX_TOKENS", str(got))


class UsesRegistryTests(unittest.TestCase):
    def test_every_use_has_a_prompt_setting_and_the_switchable_ones_a_switch(self):
        for use_id, use in ai_prompts.USES.items():
            self.assertEqual(settings.REGISTRY[f"ai.prompt.{use_id}"].default, use.default.strip())
            self.assertEqual(f"ai.use.{use_id}" in settings.REGISTRY, use.switchable, use_id)
            if use.switchable:
                self.assertIs(settings.REGISTRY[f"ai.use.{use_id}"].default, True)  # as before: on

    def test_the_four_places_that_use_the_ai_today(self):
        self.assertEqual(
            {i for i, u in ai_prompts.USES.items() if u.switchable},
            {"new_game", "completed_game", "ranking_games", "ranking_players"},
        )


class PromptOverrideTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.code = settings.REGISTRY["ai.prompt.new_game"].default

    def test_without_an_override_the_code_prompt_applies(self):
        self.assertEqual(settings.get_all(self.db)["ai.prompt.new_game"], self.code)
        self.assertFalse(next(u for u in settings.ai_uses(self.db) if u["id"] == "new_game")["customized"])

    def test_the_database_prompt_wins_over_the_code(self):
        settings.set_values(self.db, {"ai.prompt.new_game": "  Di algo corto.  "})
        self.assertEqual(settings.get_all(self.db)["ai.prompt.new_game"], "Di algo corto.")
        view = next(u for u in settings.ai_uses(self.db) if u["id"] == "new_game")
        self.assertTrue(view["customized"])
        self.assertEqual(view["default_prompt"], self.code)  # the panel can still offer the original

    def test_none_restores_the_code_prompt_by_deleting_the_override(self):
        settings.set_values(self.db, {"ai.prompt.new_game": "Mío"})
        self.assertEqual(settings.set_values(self.db, {"ai.prompt.new_game": None}), ["ai.prompt.new_game"])
        self.assertEqual(settings.get_all(self.db)["ai.prompt.new_game"], self.code)
        self.assertEqual(self.db.query(models.AppSetting).filter_by(key="ai.prompt.new_game").count(), 0)
        self.assertEqual(settings.set_values(self.db, {"ai.prompt.new_game": None}), [])  # already the default

    def test_only_resettable_settings_accept_none(self):
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"ai.provider": None})

    def test_prompts_cannot_be_empty_or_huge(self):
        for bad in ("", "   ", "x" * (settings.PROMPT_MAX + 1)):
            with self.assertRaises(ValueError):
                settings.set_values(self.db, {"ai.prompt.new_game": bad})

    def test_a_bad_value_changes_nothing_not_even_the_valid_ones(self):
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"ai.prompt.new_game": "Mío", "ai.prompt.ranking_games": ""})
        self.assertEqual(self.db.query(models.AppSetting).count(), 0)


class PerUseTests(unittest.TestCase):
    def stored(self, **overrides):
        """settings.get as production answers it: what is stored, else the default of the registry."""
        base = {"ai.enabled": True, "ai.api_key": KEY}
        return mock.patch.object(
            ai.settings, "get", side_effect=lambda k: {**base, **overrides}.get(k, settings.REGISTRY[k].default)
        )

    def test_each_use_has_its_own_switch(self):
        with self.stored(**{"ai.use.new_game": False}):
            self.assertFalse(ai.is_ready("new_game"))
            self.assertTrue(ai.is_ready("completed_game"))
            self.assertTrue(ai.is_ready())

    def test_the_general_switch_wins_over_the_ones_of_each_use(self):
        with self.stored(**{"ai.enabled": False}):
            self.assertFalse(ai.is_ready("completed_game"))

    def test_the_prompt_is_the_stored_one_plus_the_recommendation_fragment(self):
        with self.stored(**{"ai.prompt.completed_game": "MI PROMPT", "ai.prompt.completed_game_recommendation": "MI RECOMENDACION"}):
            self.assertEqual(ai.prompt_for("completed_game"), "MI PROMPT")
            text = ai.prompt_for("completed_game", {"game": "Hades", "user": "Bob"})
        self.assertEqual(text.splitlines()[:2], ["MI PROMPT", "MI RECOMENDACION"])
        self.assertTrue(text.endswith("Juego recomendado: Hades\nJugado por: Bob"))


class NoticeSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def send(self, **overrides):
        from tests.test_recommendations import FakeBot

        FakeBot.sent = []
        base = {
            "notifications.enabled": True, "telegram.token": "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345",
            "telegram.group_id": "-100", "ai.enabled": True, "ai.api_key": KEY,
        }
        complete = mock.Mock(return_value="Reescrito por la IA")
        with mock.patch.object(my_utils.telegram, "Bot", FakeBot), \
                mock.patch.object(my_utils.settings, "get", side_effect=lambda k: {**base, **overrides}.get(k, settings.REGISTRY[k].default)), \
                mock.patch.object(my_utils.ai, "complete", complete):
            await my_utils.send_message("Ana completó Doom", False, ai_use="completed_game", new_game_recommended={"game": "Hades", "user": "Bob"})
        return complete, FakeBot.sent[0]["text"]

    async def test_with_the_use_on_the_ai_writes_it(self):
        complete, text = await self.send()
        self.assertEqual(text, "Reescrito por la IA")
        self.assertIn(settings.REGISTRY["ai.prompt.completed_game"].default, complete.call_args.args[0])

    async def test_with_the_use_off_the_original_goes_out_with_the_plain_recommendation(self):
        complete, text = await self.send(**{"ai.use.completed_game": False})
        complete.assert_not_called()
        self.assertTrue(text.startswith("Ana completó Doom"))
        self.assertIn("Lo tiene Bob", text)

    async def test_the_admin_prompt_is_what_reaches_the_ai(self):
        complete, _ = await self.send(**{"ai.prompt.completed_game": "SOLO UN EMOJI"})
        self.assertTrue(complete.call_args.args[0].startswith("SOLO UN EMOJI"))


class TestRouteTests(unittest.TestCase):
    admin = mock.Mock(username="root")

    def test_without_a_key_it_says_so(self):
        with values(**{"ai.api_key": None}), self.assertRaises(HTTPException) as caught:
            manage.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 409)

    def test_it_works_with_the_switch_off_and_reports_what_was_used(self):
        with values(**{"ai.enabled": False}), mock.patch.dict(ai.PROVIDERS, {"google": mock.Mock(return_value="Hola")}):
            result = manage.test_ai(self.admin)
        self.assertEqual(result["reply"], "Hola")
        self.assertEqual((result["provider"], result["model"]), ("google", "gemini-2.5-flash"))

    def test_a_provider_failure_is_a_502_with_the_reason(self):
        failing = mock.Mock(side_effect=AIError("Google respondio 403: no"))
        with values(), mock.patch.dict(ai.PROVIDERS, {"google": failing}):
            with self.assertRaises(HTTPException) as caught:
                manage.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("403", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest import mock

from fastapi import HTTPException
from google.genai import errors, types

from src.clients import google_ai
from src.clients.ai_error import AIError
from src.database import models
from src.routers.manage import system
from src.utils import ai, ai_prompts, my_utils, settings
from tests.sqlite_db import make_session

KEY = "AIzaSyFAKE-key-for-tests-0123456789"
OTHER_KEY = "AIzaSyNEWKEY-0123456789-abcdef"


def values(**overrides):
    base = {"ai.enabled": True, "ai.provider": "google", "ai.api_key": KEY, "ai.model": "gemini-test"}
    return mock.patch.object(ai.settings, "get", side_effect=lambda k: {**base, **overrides}[k])


class SettingsTests(unittest.TestCase):
    def test_the_provider_comes_only_from_the_environment_and_has_no_default(self):
        db = make_session()
        with mock.patch.dict(os.environ, {"AI_PROVIDER": " openai "}):
            self.assertEqual(settings.get("ai.provider"), "openai")
            self.assertEqual(settings.public_view(db)["ai.provider"], {"is_set": True, "hint": None})
            with self.assertRaises(ValueError):
                settings.set_values(db, {"ai.provider": "google"})  # not from the panel
        with mock.patch.dict(os.environ, {"AI_PROVIDER": ""}):
            self.assertIsNone(settings.get("ai.provider"))
        self.assertEqual(db.query(models.AppSetting).filter_by(key="ai.provider").count(), 0)

    def test_the_model_comes_only_from_the_environment_and_has_no_default(self):
        db = make_session()
        with mock.patch.dict(os.environ, {"AI_MODEL": "gemini-x", "OPENAI_MODEL": ""}):
            self.assertEqual(settings.get("ai.model"), "gemini-x")
            self.assertEqual(settings.public_view(db)["ai.model"], {"is_set": True, "hint": None})
            with self.assertRaises(ValueError):
                settings.set_values(db, {"ai.model": "other"})  # not from the panel
        with mock.patch.dict(os.environ, {"AI_MODEL": "", "OPENAI_MODEL": ""}):
            self.assertIsNone(settings.get("ai.model"))  # nothing in the code fills the gap
            self.assertEqual(settings.public_view(db)["ai.model"], {"is_set": False, "hint": None})
        with mock.patch.dict(os.environ, {"AI_MODEL": "", "OPENAI_MODEL": "gpt-old"}):
            self.assertEqual(settings.get("ai.model"), "gpt-old")  # the old variable still gives it
        self.assertEqual(db.query(models.AppSetting).filter_by(key="ai.model").count(), 0)

    def test_the_key_comes_from_the_environment_is_never_stored_and_never_shown(self):
        db = make_session()
        with mock.patch.dict(os.environ, {"AI_API_KEY": KEY}):
            self.assertEqual(settings.get("ai.api_key"), KEY)
            self.assertEqual(settings.public_view(db)["ai.api_key"], {"is_set": True, "hint": None})
            self.assertNotIn(KEY, str(settings.public_view(db)))
            with self.assertRaises(ValueError):
                settings.set_values(db, {"ai.api_key": OTHER_KEY})  # not from the panel
        self.assertEqual(db.query(models.AppSetting).filter_by(key="ai.api_key").count(), 0)
        with mock.patch.dict(os.environ, {"AI_API_KEY": "", "OPENAI_API_KEY": ""}):
            self.assertEqual(settings.public_view(db)["ai.api_key"], {"is_set": False, "hint": None})

    def test_the_old_openai_variable_still_gives_the_key(self):
        with mock.patch.dict(os.environ, {"AI_API_KEY": "", "OPENAI_API_KEY": "sk-old"}):
            self.assertEqual(settings.get("ai.api_key"), "sk-old")
        with mock.patch.dict(os.environ, {"AI_API_KEY": KEY, "OPENAI_API_KEY": "sk-old"}):
            self.assertEqual(settings.get("ai.api_key"), KEY)  # the new one wins


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

    def test_the_panel_is_told_the_provider_and_the_model_in_use(self):
        with values():
            self.assertEqual(ai.in_use(), {"provider": "google", "model": "gemini-test"})
        with values(**{"ai.provider": "openai", "ai.model": "gpt-x"}):
            self.assertEqual(ai.in_use(), {"provider": "openai", "model": "gpt-x"})
        with values(**{"ai.model": None, "ai.provider": None}):
            self.assertEqual(ai.in_use(), {"provider": None, "model": None})

    def test_without_a_provider_or_a_model_the_ai_writes_nothing_and_calls_nobody(self):
        provider = mock.Mock()
        for missing in ({"ai.model": None}, {"ai.provider": None}, {"ai.provider": "claude"}):
            with mock.patch.dict(ai.PROVIDERS, {"google": provider}), values(**missing):
                self.assertFalse(ai.is_ready(), missing)
                self.assertFalse(ai.is_ready("new_game"), missing)
                self.assertIsNone(ai.complete("s", "u"), missing)
                self.assertIsNone(ai.complete("s", "u", force=True), missing)
        provider.assert_not_called()

    def test_the_provider_model_and_key_come_from_the_settings(self):
        google, openai = mock.Mock(return_value="g"), mock.Mock(return_value="o")
        with mock.patch.dict(ai.PROVIDERS, {"google": google, "openai": openai}):
            with values():
                self.assertEqual(ai.complete("sys", "usr"), "g")
            google.assert_called_once_with(KEY, "gemini-test", "sys", "usr", 1.0)
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

    def test_the_places_that_use_the_ai_today(self):
        self.assertEqual(
            {i for i, u in ai_prompts.USES.items() if u.switchable},
            {"new_game", "completed_game", "ranking_games", "ranking_players", "wishlist_release"},
        )


class PromptOverrideTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.code = settings.REGISTRY["ai.prompt.new_game"].default

    def test_without_an_override_the_code_prompt_applies(self):
        self.assertEqual(settings.get_all(self.db)["ai.prompt.new_game"], self.code)
        self.assertFalse(next(u for u in settings.ai_uses(self.db) if u["id"] == "new_game")["customized"])

    def test_a_fragment_says_which_notice_it_belongs_to_and_the_notices_belong_to_none(self):
        uses = {u["id"]: u for u in settings.ai_uses(self.db)}
        self.assertEqual(uses["completed_game_recommendation"]["parent"], "completed_game")
        self.assertFalse(uses["completed_game_recommendation"]["switchable"])
        self.assertTrue(all(u["parent"] is None for u in uses.values() if u["switchable"]))

    def test_every_use_names_the_setting_of_its_switch_and_it_exists(self):
        for use in settings.ai_uses(self.db):
            self.assertIn(use["switch"], settings.REGISTRY, use["id"])
            self.assertEqual(use["switch"].startswith("ai.use."), use["switchable"], use["id"])

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
            settings.set_values(self.db, {"weekly.weekday": None})

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
        base = {"ai.enabled": True, "ai.provider": "google", "ai.api_key": KEY, "ai.model": "gemini-test"}
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
            text = ai.prompt_for("completed_game", {"game": "Hades", "reasons": ["Comparte género: RPG", "Lo tienen 2 jugadores del grupo"]})
            plain = ai.prompt_for("completed_game", {"game": "Hades", "reasons": []})
        self.assertEqual(text.splitlines()[:2], ["MI PROMPT", "MI RECOMENDACION"])
        self.assertTrue(text.endswith("Juego recomendado: Hades\nMotivos:\n- Comparte género: RPG\n- Lo tienen 2 jugadores del grupo"))
        self.assertTrue(plain.endswith("Juego recomendado: Hades"))  # no reasons, no heading
        self.assertNotIn("Jugado por", text)  # who has the game is never told


class NoticeSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def send(self, **overrides):
        from tests.test_recommendations import FakeBot

        FakeBot.sent = []
        base = {
            "notifications.enabled": True, "telegram.token": "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345",
            "telegram.group_id": "-100", "ai.enabled": True, "ai.provider": "google", "ai.api_key": KEY, "ai.model": "gemini-test",
        }
        complete = mock.Mock(return_value="Reescrito por la IA")
        with mock.patch.object(my_utils.telegram, "Bot", FakeBot), \
                mock.patch.object(my_utils.settings, "get", side_effect=lambda k: {**base, **overrides}.get(k, settings.REGISTRY[k].default)), \
                mock.patch.object(my_utils.ai, "complete", complete):
            await my_utils.send_message("Ana completó Doom", False, ai_use="completed_game", new_game_recommended={"game": "Hades", "reasons": []})
        return complete, FakeBot.sent[0]["text"]

    async def test_with_the_use_on_the_ai_writes_it(self):
        complete, text = await self.send()
        self.assertEqual(text, "Reescrito por la IA")
        self.assertIn(settings.REGISTRY["ai.prompt.completed_game"].default, complete.call_args.args[0])

    async def test_with_the_use_off_the_original_goes_out_with_the_plain_recommendation(self):
        complete, text = await self.send(**{"ai.use.completed_game": False})
        complete.assert_not_called()
        self.assertTrue(text.startswith("Ana completó Doom"))
        self.assertIn("¿Te apetece probar *Hades*?", text)
        self.assertNotIn("Lo tiene", text)

    async def test_the_admin_prompt_is_what_reaches_the_ai(self):
        complete, _ = await self.send(**{"ai.prompt.completed_game": "SOLO UN EMOJI"})
        self.assertTrue(complete.call_args.args[0].startswith("SOLO UN EMOJI"))


class TestRouteTests(unittest.TestCase):
    admin = mock.Mock(username="root")

    def test_without_a_key_it_says_so(self):
        with values(**{"ai.api_key": None}), self.assertRaises(HTTPException) as caught:
            system.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 409)

    def test_without_a_provider_or_a_model_it_is_a_409_that_says_where_to_set_them(self):
        for missing in ({"ai.model": None}, {"ai.provider": None}):
            with values(**missing), self.assertRaises(HTTPException) as caught:
                system.test_ai(self.admin)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertIn("AI_MODEL", caught.exception.detail)
            self.assertIn("AI_PROVIDER", caught.exception.detail)

    def test_it_works_with_the_switch_off_and_reports_what_was_used(self):
        with values(**{"ai.enabled": False}), mock.patch.dict(ai.PROVIDERS, {"google": mock.Mock(return_value="Hola")}):
            result = system.test_ai(self.admin)
        self.assertEqual(result["reply"], "Hola")
        self.assertEqual((result["provider"], result["model"]), ("google", "gemini-test"))

    def test_a_provider_failure_is_a_502_with_the_reason(self):
        failing = mock.Mock(side_effect=AIError("Google respondio 403: no"))
        with values(), mock.patch.dict(ai.PROVIDERS, {"google": failing}):
            with self.assertRaises(HTTPException) as caught:
                system.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("403", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

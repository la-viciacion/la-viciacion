import os
import unittest
from unittest import mock

from fastapi import HTTPException

from src.clients.ai_error import AIError
from src.database import models
from src.routers.manage import system
from src.utils import ai, ai_build, ai_prompts, ai_providers, my_utils, settings
from tests import ai_env
from tests.sqlite_db import make_session


# `ai.complete` writes the record of a notice in a session of its own, which these tests have no database for
_no_record = mock.patch.object(ai.ai_ledger, "record_notice")


def setUpModule():
    _no_record.start()


def tearDownModule():
    _no_record.stop()

KEY = "AIzaSyFAKE-key-for-tests-0123456789"
OTHER_KEY = "AIzaSyNEWKEY-0123456789-abcdef"


def values(**overrides):
    base = ai_env.group("google", KEY, "gemini-test", **{"ai.enabled": True})
    return mock.patch.object(ai.settings, "get", side_effect=lambda k: {**base, **overrides}[k])


class SettingsTests(unittest.TestCase):
    def test_the_keys_and_default_models_come_only_from_the_environment_per_provider(self):
        db = make_session()
        env = {"OPENAI_AI_API_KEY": KEY, "OPENAI_AI_MODEL": " gpt-x ", "OPENAI_CHAT_AI_MODEL": "gpt-strong", "GOOGLE_AI_API_KEY": "", "GOOGLE_AI_MODEL": "gemini-x"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(settings.get("ai.openai.api_key"), KEY)
            self.assertEqual(settings.get("ai.openai.model"), "gpt-x")
            self.assertEqual(settings.get("ai.openai.chat_model"), "gpt-strong")
            self.assertIsNone(settings.get("ai.google.api_key"))
            view = settings.public_view(db)
            self.assertEqual(view["ai.openai.api_key"], {"is_set": True, "hint": None})
            self.assertEqual(view["ai.google.api_key"], {"is_set": False, "hint": None})
            self.assertNotIn(KEY, str(view))
            for key in ("ai.openai.api_key", "ai.openai.model", "ai.google.chat_model"):
                with self.assertRaises(ValueError):
                    settings.set_values(db, {key: "other"})  # not from the panel
        for p in settings.AI_PROVIDERS:
            self.assertIsNone(settings.REGISTRY[f"ai.{p}.model"].default)  # nothing in the code fills the gap
        self.assertEqual(db.query(models.AppSetting).count(), 0)

    def test_the_old_variables_are_gone(self):
        for old in ("ai.api_key", "ai.model", "chat.model"):
            self.assertNotIn(old, settings.REGISTRY)
        self.assertFalse(settings.REGISTRY["ai.provider"].env_only)  # the provider is picked in the panel, not in the .env

    def test_what_the_panel_picks_is_stored_and_checked(self):
        db = make_session()
        settings.set_values(db, {"ai.provider": "google", "ai.model.google": "gemini-2.5-flash", "chat.model.openai": "gpt-4.1"})
        self.assertEqual(settings.get_all(db)["ai.provider"], "google")
        with self.assertRaises(ValueError):
            settings.set_values(db, {"ai.provider": "claude"})
        with self.assertRaises(ValueError):
            settings.set_values(db, {"ai.model.openai": "no valid name!"})
        settings.set_values(db, {"ai.provider": None})  # back to "the first with a key"
        self.assertIsNone(settings.get_all(db)["ai.provider"])

    def test_the_providers_of_the_registry_are_the_ones_that_can_write(self):
        self.assertEqual(set(ai_build._CLASSES), set(settings.AI_PROVIDERS))


class ProviderChoiceTests(unittest.TestCase):
    def table(self, **overrides):
        base = {**ai_env.group(None), "ai.openai.api_key": "O", "ai.google.api_key": "G", "ai.openai.model": "gpt-d", "ai.google.model": "gem-d"}
        return mock.patch.object(ai_providers.settings, "get", side_effect=lambda k: {**base, **overrides}[k])

    def test_the_providers_are_those_with_a_key(self):
        with self.table():
            self.assertEqual(ai_providers.available(), ["openai", "google"])
        with self.table(**{"ai.openai.api_key": None}):
            self.assertEqual(ai_providers.available(), ["google"])
        with self.table(**{"ai.openai.api_key": None, "ai.google.api_key": None}):
            self.assertEqual(ai_providers.available(), [])
            self.assertIsNone(ai_providers.selected())
            self.assertIsNone(ai_providers.group_credentials())

    def test_with_both_the_pick_decides_and_with_none_the_first_is_used(self):
        with self.table():
            self.assertEqual(ai_providers.selected(), "openai")
        with self.table(**{"ai.provider": "google"}):
            self.assertEqual(ai_providers.current(), ("google", "gem-d"))
            self.assertEqual(ai_providers.group_credentials(), ("google", "G", "gem-d"))

    def test_a_provider_with_a_key_and_no_model_does_not_hide_one_that_is_complete(self):
        with self.table(**{"ai.openai.model": None}):
            self.assertEqual(ai_providers.selected(), "google")
            self.assertEqual(ai_providers.group_credentials(), ("google", "G", "gem-d"))
            self.assertEqual(ai_providers.selected(ai_providers.CHAT), "google", "the chat follows the notices")
        with self.table(**{"ai.openai.model": None, "ai.model.openai": "gpt-picked"}):
            self.assertEqual(ai_providers.selected(), "openai", "a model picked in the panel is a model")

    def test_with_no_provider_complete_the_first_with_a_key_is_still_the_one_the_panel_asks_about(self):
        with self.table(**{"ai.openai.model": None, "ai.google.model": None}):
            self.assertEqual(ai_providers.selected(), "openai")
            self.assertIsNone(ai_providers.group_credentials())

    def test_a_pick_is_respected_even_without_a_model(self):
        with self.table(**{"ai.provider": "openai", "ai.openai.model": None}):
            self.assertEqual(ai_providers.selected(), "openai")
            self.assertIsNone(ai_providers.group_credentials(), "the panel says the model is missing")

    def test_a_pick_whose_provider_lost_its_key_is_ignored(self):
        with self.table(**{"ai.provider": "google", "ai.google.api_key": None}):
            self.assertEqual(ai_providers.selected(), "openai")

    def test_the_model_picked_in_the_panel_wins_over_the_env_default_and_is_per_provider(self):
        with self.table(**{"ai.model.openai": "gpt-picked", "ai.provider": "openai"}):
            self.assertEqual(ai_providers.model(), "gpt-picked")
            self.assertEqual(ai_providers.model(provider="google"), "gem-d")
            self.assertTrue(ai_providers.own_model(ai_providers.NOTICES, "openai"))
            self.assertFalse(ai_providers.own_model(ai_providers.NOTICES, "google"))

    def test_the_chat_model_falls_back_to_the_notices_one(self):
        with self.table(**{"ai.openai.chat_model": "gpt-chat"}):
            self.assertEqual(ai_providers.model(ai_providers.CHAT), "gpt-chat")
        with self.table(**{"ai.model.openai": "gpt-picked"}):
            self.assertEqual(ai_providers.model(ai_providers.CHAT), "gpt-picked")  # no chat model of its own at all
        with self.table(**{"ai.openai.chat_model": "gpt-chat", "chat.model.openai": "gpt-chat-picked"}):
            self.assertEqual(ai_providers.model(ai_providers.CHAT), "gpt-chat-picked")


class PerUseProviderTests(unittest.TestCase):
    def table(self, **overrides):
        base = {**ai_env.group(None), "ai.openai.api_key": "O", "ai.google.api_key": "G", "ai.openai.model": "gpt-d", "ai.google.model": "gem-d"}
        return mock.patch.object(ai_providers.settings, "get", side_effect=lambda k: {**base, **overrides}[k])

    def test_the_chat_follows_the_notices_and_the_guide_follows_the_chat_until_one_is_picked(self):
        with self.table(**{"ai.provider": "google"}):
            self.assertEqual([ai_providers.selected(u) for u in ai_providers.USES], ["google"] * 3)
        with self.table(**{"ai.provider": "google", "chat.provider": "openai"}):
            self.assertEqual([ai_providers.selected(u) for u in ai_providers.USES], ["google", "openai", "openai"])
        with self.table(**{"ai.provider": "google", "chat.provider": "openai", "guide.provider": "google"}):
            self.assertEqual([ai_providers.selected(u) for u in ai_providers.USES], ["google", "openai", "google"])

    def test_each_use_picks_its_own_model_and_falls_back_to_what_it_follows(self):
        with self.table(**{"chat.model.openai": "gpt-chat"}):
            self.assertEqual(ai_providers.model(ai_providers.GUIDE), "gpt-chat")  # the guide follows the chat's model
            self.assertEqual(ai_providers.model(ai_providers.NOTICES), "gpt-d")
        with self.table(**{"chat.model.openai": "gpt-chat", "guide.model.openai": "gpt-search"}):
            self.assertEqual(ai_providers.model(ai_providers.GUIDE), "gpt-search")
            self.assertEqual(ai_providers.model(ai_providers.CHAT), "gpt-chat")

    def test_a_pick_without_a_key_is_ignored_per_use(self):
        with self.table(**{"guide.provider": "google", "ai.google.api_key": None}):
            self.assertEqual(ai_providers.selected(ai_providers.GUIDE), "openai")

    def test_the_credentials_of_a_use_are_those_of_its_provider(self):
        with self.table(**{"chat.provider": "google", "guide.model.openai": "gpt-search"}):
            self.assertEqual(ai_providers.group_credentials(ai_providers.CHAT), ("google", "G", "gem-d"))
            self.assertEqual(ai_providers.group_credentials(ai_providers.GUIDE), ("google", "G", "gem-d"))
            self.assertEqual(ai_providers.group_credentials(ai_providers.NOTICES), ("openai", "O", "gpt-d"))

    def test_the_panel_is_told_what_each_use_runs_on(self):
        with self.table(**{"chat.provider": "google"}):
            uses = ai_providers.status()["uses"]
        self.assertEqual(uses["notices"]["provider"], "openai")
        self.assertEqual((uses["chat"]["provider"], uses["chat"]["picked"]), ("google", "google"))
        self.assertEqual((uses["guide"]["provider"], uses["guide"]["picked"]), ("google", None))


class CompleteTests(unittest.TestCase):
    def test_off_or_without_a_key_it_answers_nothing_and_calls_nobody(self):
        with ai_env.using(ai_env.says()) as build:
            with values(**{"ai.enabled": False}):
                self.assertIsNone(ai.complete("s", "u"))
                self.assertFalse(ai.is_ready())
            with values(**{"ai.google.api_key": None}):
                self.assertIsNone(ai.complete("s", "u"))
                self.assertIsNone(ai.complete("s", "u", force=True))
        build.assert_not_called()

    def test_force_ignores_the_switch(self):
        with ai_env.using(ai_env.says("hola")), values(**{"ai.enabled": False}):
            self.assertEqual(ai.complete("s", "u", force=True), "hola")

    def test_the_panel_is_told_the_provider_and_the_model_in_use(self):
        with values():
            self.assertEqual(ai.in_use(), {"provider": "google", "model": "gemini-test", "problem": None})
        with values(**ai_env.group("openai", KEY, "gpt-x")):
            self.assertEqual(ai.in_use(), {"provider": "openai", "model": "gpt-x", "problem": None})
        with values(**ai_env.group(None)):
            self.assertEqual(ai.in_use(), {"provider": None, "model": None, "problem": None})

    def test_without_a_key_or_a_model_the_ai_writes_nothing_and_calls_nobody(self):
        for missing in ({"ai.google.model": None}, ai_env.group(None)):
            with ai_env.using(ai_env.says()) as build, values(**missing):
                self.assertFalse(ai.is_ready(), missing)
                self.assertFalse(ai.is_ready("new_game"), missing)
                self.assertIsNone(ai.complete("s", "u"), missing)
                self.assertIsNone(ai.complete("s", "u", force=True), missing)
            build.assert_not_called()

    def test_the_provider_model_and_key_come_from_the_settings(self):
        with ai_env.using(ai_env.says("g")) as build, values():
            self.assertEqual(ai.complete("sys", "usr"), "g")
        build.assert_called_once_with("google", "gemini-test", KEY)
        with ai_env.using(ai_env.says("o")) as build, values(**ai_env.group("openai", KEY, "gpt-x")):
            self.assertEqual(ai.complete("sys", "usr"), "o")
        build.assert_called_once_with("openai", "gpt-x", KEY)

    def test_the_model_gets_the_instructions_the_text_and_the_temperature(self):
        seen = []
        with ai_env.using(ai_env.says(seen=seen)), values():
            ai.complete("sys", "usr")
        (messages, model_settings), = seen
        self.assertEqual((messages[0].instructions, messages[0].parts[0].content), ("sys", "usr"))
        self.assertEqual((model_settings["temperature"], model_settings["timeout"]), (1.0, ai.TIMEOUT_SECONDS))

    def test_a_temperature_above_what_anthropic_accepts_is_lowered_for_everybody(self):
        seen = []
        with ai_env.using(ai_env.says(seen=seen)), values():
            ai.complete("s", "u", temperature=1.8)
        self.assertEqual(seen[0][1]["temperature"], ai.MAX_TEMPERATURE)

    def test_the_model_of_the_group_is_built_once_and_not_for_every_notice(self):
        with ai_env.using(ai_env.says("a")) as build, values():
            ai.complete("s", "u")
            ai.complete("s", "u")
        build.assert_called_once()

    def test_an_empty_answer_says_how_it_ended(self):
        with ai_env.using(ai_env.says("   ", finish_reason="stop")), values(), self.assertRaisesRegex(AIError, r"sin texto \(stop\)"):
            ai.complete("s", "u")

    def test_an_answer_cut_before_any_text_is_explained_by_the_library_and_the_reason_reaches_the_admin(self):
        with ai_env.using(ai_env.says("", finish_reason="length")), values(), self.assertRaisesRegex(AIError, "token limit"):
            ai.complete("s", "u")

    def test_the_text_is_trimmed_and_an_empty_answer_is_an_error(self):
        with ai_env.using(ai_env.says("  hola \n")), values():
            self.assertEqual(ai.complete("s", "u"), "hola")
        with ai_env.using(ai_env.says("   ")), values(), self.assertRaisesRegex(AIError, "sin texto"):
            ai.complete("s", "u")

    def test_a_failure_never_quotes_the_key(self):
        with ai_env.using(ai_env.fails(RuntimeError(f"bad key {KEY}"))), values():
            with self.assertRaises(AIError) as caught:
                ai.complete("s", "u")
        self.assertNotIn(KEY, str(caught.exception))


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
            {"new_game", "completed_game", "ranking_games", "ranking_players", "wishlist_release", "wishlist_day", "wishlist_week", "welcome"},
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
        base = ai_env.group("google", KEY, "gemini-test", **{"ai.enabled": True})
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
            "telegram.group_id": "-100", **ai_env.group("google", KEY, "gemini-test"), "ai.enabled": True,
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
        with values(**ai_env.group(None)), self.assertRaises(HTTPException) as caught:
            system.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 409)

    def test_without_a_model_it_is_a_409_that_says_where_to_set_it(self):
        with values(**{"ai.google.model": None}), self.assertRaises(HTTPException) as caught:
            system.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("GOOGLE_AI_MODEL", caught.exception.detail)

    def test_without_any_key_it_names_the_variables_of_every_provider(self):
        with values(**ai_env.group(None)), self.assertRaises(HTTPException) as caught:
            system.test_ai(self.admin)
        self.assertIn("OPENAI_AI_API_KEY", caught.exception.detail)
        self.assertIn("GOOGLE_AI_API_KEY", caught.exception.detail)

    def test_it_works_with_the_switch_off_and_reports_what_was_used(self):
        with values(**{"ai.enabled": False}), ai_env.using(ai_env.says("Hola")):
            result = system.test_ai(self.admin)
        self.assertEqual(result["reply"], "Hola")
        self.assertEqual((result["provider"], result["model"]), ("google", "gemini-test"))

    def test_a_provider_failure_is_a_502_with_the_reason(self):
        with values(), ai_env.using(ai_env.fails(AIError("Google respondio 403: no"))):
            with self.assertRaises(HTTPException) as caught:
                system.test_ai(self.admin)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("403", caught.exception.detail)

class ModelListTests(unittest.TestCase):
    admin = mock.Mock(username="root")

    def test_it_asks_the_provider_for_its_models_now_and_offers_the_defaults(self):
        table = ai_env.group("openai", KEY, "gpt-d", **{"ai.openai.chat_model": "gpt-c"})
        with mock.patch.object(ai.settings, "get", side_effect=lambda k: table[k]),                 mock.patch.object(system.model_list, "list_models", return_value=["gpt-4.1", "gpt-4.1-2025-04-14", "text-embedding-3-small", "whisper-1"]) as listed:
            result = system.list_ai_models("openai", self.admin)
        listed.assert_called_once_with("openai", KEY)
        self.assertEqual(result["models"], ["gpt-4.1"])  # only the ones that write text, without the dated copies
        self.assertEqual(result["defaults"], {"notices": "gpt-d", "chat": "gpt-c"})

    def test_google_lists_its_own(self):
        table = ai_env.group("google", KEY, "gem-d")
        with mock.patch.object(ai.settings, "get", side_effect=lambda k: table[k]),                 mock.patch.object(system.model_list, "list_models", return_value=["gemini-2.5-flash"]):
            self.assertEqual(system.list_ai_models("google", self.admin)["models"], ["gemini-2.5-flash"])

    def test_without_the_key_of_that_provider_it_is_a_409_that_names_the_variable(self):
        table = ai_env.group("google", KEY, "gem-d")
        with mock.patch.object(ai.settings, "get", side_effect=lambda k: table[k]), self.assertRaises(HTTPException) as caught:
            system.list_ai_models("openai", self.admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("OPENAI_AI_API_KEY", caught.exception.detail)

    def test_a_provider_failure_is_a_502(self):
        table = ai_env.group("openai", KEY, "gpt-d")
        with mock.patch.object(ai.settings, "get", side_effect=lambda k: table[k]),                 mock.patch.object(system.model_list, "list_models", side_effect=AIError("boom")), self.assertRaises(HTTPException) as caught:
            system.list_ai_models("openai", self.admin)
        self.assertEqual(caught.exception.status_code, 502)



if __name__ == "__main__":
    unittest.main()

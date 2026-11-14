"""A player's own AI keys, one for each provider: how they are kept (sealed in a vault that only their password opens, bound to the player
and the provider, never returned), the keys of the old scheme, whose key pays for each question, what the player is told when their own
key is the one that fails, and the routes that unlock, save, change, try and remove them."""
import types
import unittest
from unittest import mock

import jwt
from bcrypt import gensalt, hashpw
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src import auth
from src.chat import agent as chat_agent
from src.chat import limits as chat_limits
from src.clients import failure
from src.clients.ai_error import AIError, ProviderError, Quota, QuotaError
from src.database import models
from src.guide import limits as guide_limits
from src.routers import chat as chat_router
from src.routers import user_ai as route
from src.utils import ai_models, ai_source, ai_vault, messages, settings, user_ai
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_chat import seed

KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
OTHER_KEY = "sk-proj-ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"
ANTHROPIC_KEY = "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
OPENROUTER_KEY = "sk-or-v1-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdef"
GOOGLE_KEY = "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456"
PASSWORD = "Una-Contrasena-Muy-Larga-1!"


def values(**overrides):
    base = {key: spec.default for key, spec in settings.REGISTRY.items()}
    return {**base, **ai_env.group("openai", "GROUPKEY", "gpt-4.1-mini"), **overrides}


def patched(**overrides):
    table = values(**overrides)
    return mock.patch.object(settings, "get", side_effect=lambda key: table[key])


class KeyStorageTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini")

    def test_what_is_stored_is_not_the_key_and_opens_only_with_the_data_key_for_its_player_and_provider(self):
        row = self.db.get(models.UserAiKey, (1, "openai"))
        self.assertNotIn(KEY, row.secret)
        self.assertNotIn("sk-", row.secret)
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "openai"), (KEY, "gpt-4.1-mini"))
        self.assertIsNone(user_ai.credentials(self.db, 1, b"\x09" * 32, "openai"), "another data key")
        self.assertIsNone(user_ai.credentials(self.db, 1, None, "openai"), "a locked session")
        self.assertIsNone(user_ai.credentials(self.db, 1, self.dek, "anthropic"), "no key for that provider")

    def test_the_hint_is_inside_the_sealed_value_and_no_column_holds_any_part_of_the_key(self):
        row = self.db.get(models.UserAiKey, (1, "openai"))
        for column in (row.secret, row.model, row.provider):
            self.assertNotIn(KEY[-4:], str(column))
        self.assertEqual(user_ai.status(self.db, 1, self.dek)["keys"]["openai"]["hint"], "6789")

    def test_the_status_never_shows_the_key_and_a_locked_session_sees_no_hint(self):
        status = user_ai.status(self.db, 1, self.dek)
        self.assertEqual((status["unlocked"], status["locked"], status["keys"]["openai"]["has_key"], status["keys"]["openai"]["model"]), (True, False, True, "gpt-4.1-mini"))
        self.assertNotIn(KEY, str(status))
        locked = user_ai.status(self.db, 1, None)
        self.assertEqual((locked["locked"], locked["keys"]["openai"]["has_key"], locked["keys"]["openai"]["hint"], locked["keys"]["openai"]["model"]), (True, True, None, "gpt-4.1-mini"))
        self.assertEqual((user_ai.status(self.db, 2, None)["locked"], user_ai.status(self.db, 2, None)["unlocked"]), (False, False), "no keys: nothing to unlock, but nothing can be saved either")

    def test_a_key_that_does_not_open_with_the_data_key_is_unreadable_and_the_player_is_asked_for_it_again(self):
        status = user_ai.status(self.db, 1, b"\x09" * 32)
        self.assertEqual((status["keys"]["openai"]["unreadable"], status["keys"]["openai"]["hint"]), (True, None))

    def test_every_provider_has_its_own_key_and_they_are_listed_in_order(self):
        for provider, key in (("google", GOOGLE_KEY), ("openrouter", OPENROUTER_KEY), ("anthropic", ANTHROPIC_KEY)):
            user_ai.save(self.db, 1, self.dek, provider, key)
        self.assertEqual(user_ai.providers_with_key(self.db, 1), ["openai", "anthropic", "google", "openrouter"])
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "anthropic"), (ANTHROPIC_KEY, user_ai.DEFAULT_MODELS["anthropic"]))
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "openrouter")[0], OPENROUTER_KEY)

    def test_replacing_a_key_keeps_the_model_unless_one_is_given(self):
        user_ai.set_model(self.db, 1, "openai", "gpt-5")
        user_ai.save(self.db, 1, self.dek, "openai", OTHER_KEY)
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "openai"), (OTHER_KEY, "gpt-5"))
        user_ai.save(self.db, 1, self.dek, "openai", KEY, "o3")
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "openai"), (KEY, "o3"))

    def test_removing_one_leaves_the_others_and_takes_the_preference_for_it_away(self):
        user_ai.save(self.db, 1, self.dek, "google", GOOGLE_KEY)
        user_ai.set_preferred(self.db, 1, "openai")
        user_ai.clear(self.db, 1, "openai")
        self.assertEqual(user_ai.providers_with_key(self.db, 1), ["google"])
        self.assertIsNone(user_ai.preferred(self.db, 1))
        user_ai.clear(self.db, 2, "openai")  # nothing to remove: fine

    def test_the_model_can_change_only_when_there_is_a_key(self):
        self.assertFalse(user_ai.set_model(self.db, 1, "google", "gemini-x"))
        self.assertTrue(user_ai.set_model(self.db, 1, "openai", "gpt-5"))
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "openai"), (KEY, "gpt-5"))

    def test_a_key_is_only_accepted_for_its_own_provider_and_a_model_name_must_be_valid(self):
        good = {"openai": KEY, "anthropic": ANTHROPIC_KEY, "openrouter": OPENROUTER_KEY, "google": GOOGLE_KEY}
        for provider, key in good.items():
            self.assertEqual(user_ai.clean_key(provider, f"  {key} "), key, provider)
            for other in good:
                if other != provider:
                    self.assertIsNone(user_ai.clean_key(other, key), f"{provider}'s key is not {other}'s")
        for provider in good:
            for bad in ("", None, "sk-short", "hello", "sk- with spaces and more text here"):
                self.assertIsNone(user_ai.clean_key(provider, bad), (provider, bad))
        self.assertIsNone(user_ai.clean_key("nobody", KEY))
        self.assertEqual(user_ai.clean_model(" gpt-4.1-mini "), "gpt-4.1-mini")
        self.assertEqual(user_ai.clean_model("anthropic/claude-haiku-5-5"), "anthropic/claude-haiku-5-5")
        for bad in ("", None, "a b", "x" * 81, "-gpt", "gpt;drop"):
            self.assertIsNone(user_ai.clean_model(bad), bad)

    def test_it_is_not_part_of_what_a_player_can_patch_nor_of_their_preferences(self):
        from src.database import schemas
        from src.utils import user_settings

        self.assertNotIn("ai_provider", schemas.UserSettingsUpdate.model_fields)
        self.assertNotIn(KEY, str(user_settings.get(self.db, 1)))
        self.assertFalse({"ai_api_key", "ai_key_hint", "ai_model"} & set(models.UserSettings.__table__.columns.keys()), "the old columns are gone")

    def test_the_vault_and_the_keys_go_with_the_account(self):
        for table in (models.UserAiKey.__table__, models.UserAiVault.__table__):
            (key,) = table.foreign_keys
            self.assertEqual((key.column.table.name, key.ondelete), ("users", "CASCADE"))


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        patcher = mock.patch.object(ai_vault, "KDF", ai_env.FAST_KDF)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_first_unlock_makes_the_vault_and_the_next_opens_the_same_one(self):
        first = user_ai.unlock(self.db, 1, PASSWORD)
        again = user_ai.unlock(self.db, 1, PASSWORD)
        self.assertEqual((len(first), first), (32, again))
        self.assertEqual(self.db.query(models.UserAiVault).count(), 1)
        self.assertNotIn(PASSWORD, self.db.get(models.UserAiVault, 1).record)

    def test_a_login_does_not_make_a_vault_for_a_player_who_has_nothing_to_keep(self):
        self.assertIsNone(user_ai.unlock(self.db, 1, PASSWORD, create=False))
        self.assertEqual(self.db.query(models.UserAiVault).count(), 0)
        dek = user_ai.unlock(self.db, 1, PASSWORD)
        self.assertEqual(user_ai.unlock(self.db, 1, PASSWORD, create=False), dek, "once there is one, a login opens it")

    def test_a_password_that_does_not_open_the_vault_gives_nothing_and_changes_nothing(self):
        dek = user_ai.unlock(self.db, 1, PASSWORD)
        user_ai.save(self.db, 1, dek, "openai", KEY)
        self.assertIsNone(user_ai.unlock(self.db, 1, PASSWORD + "x"))
        self.assertEqual(user_ai.credentials(self.db, 1, dek, "openai")[0], KEY)

    def test_changing_the_password_wraps_the_same_data_key_again_and_the_keys_follow(self):
        dek = user_ai.unlock(self.db, 1, PASSWORD)
        user_ai.save(self.db, 1, dek, "openai", KEY)
        user_ai.rewrap(self.db, 1, PASSWORD, "La-Nueva-Contrasena-2@")
        self.assertIsNone(user_ai.unlock(self.db, 1, PASSWORD), "the old password no longer opens it")
        self.assertEqual(user_ai.unlock(self.db, 1, "La-Nueva-Contrasena-2@"), dek)
        self.assertEqual(user_ai.credentials(self.db, 1, dek, "openai")[0], KEY)

    def test_rewrapping_with_a_wrong_old_password_deletes_what_nobody_can_read_any_more(self):
        dek = user_ai.unlock(self.db, 1, PASSWORD)
        user_ai.save(self.db, 1, dek, "openai", KEY)
        user_ai.rewrap(self.db, 1, "not the old one", "La-Nueva-Contrasena-2@")
        self.assertEqual((self.db.query(models.UserAiVault).count(), self.db.query(models.UserAiKey).count()), (0, 0))

    def test_a_player_without_a_vault_has_nothing_to_rewrap(self):
        user_ai.rewrap(self.db, 1, PASSWORD, "La-Nueva-Contrasena-2@")
        self.assertEqual(self.db.query(models.UserAiVault).count(), 0)

    def test_a_reset_password_deletes_the_vault_the_keys_and_the_preference(self):
        dek = user_ai.unlock(self.db, 1, PASSWORD)
        user_ai.save(self.db, 1, dek, "openai", KEY)
        user_ai.save(self.db, 1, dek, "google", GOOGLE_KEY)
        user_ai.set_preferred(self.db, 1, "google")
        user_ai.save(self.db, 2, user_ai.unlock(self.db, 2, PASSWORD), "openai", OTHER_KEY)
        self.assertTrue(user_ai.wipe(self.db, 1))
        self.assertEqual(user_ai.providers_with_key(self.db, 1), [])
        self.assertIsNone(user_ai.preferred(self.db, 1))
        self.assertEqual(user_ai.providers_with_key(self.db, 2), ["openai"], "only that player's")
        self.assertFalse(user_ai.wipe(self.db, 1), "nothing left to delete")


class WhoPaysTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)

    def resolve(self, feature, mode, own=False, group=True, enabled=True, provider="openai", key=KEY, locked=False):
        dek = None
        for p in user_ai.PROVIDERS:  # a player with exactly the keys this call says
            user_ai.clear(self.db, 1, p)
        if own:
            dek = ai_env.give_key(self.db, 1, key, "gpt-5-mini", provider)
            dek = None if locked else dek
        groupkey = "GROUPKEY" if group else None
        with patched(**{f"{feature}.key_source": mode, f"{feature}.enabled": enabled, "ai.openai.api_key": groupkey}):
            return ai_source.resolve(self.db, 1, feature, dek), ai_source.availability(self.db, 1, feature, dek)

    def test_user_only_uses_the_players_key_and_nothing_else(self):
        source, state = self.resolve("guide", "user_only", own=True)
        self.assertEqual((source.key_source, source.api_key, source.model, source.provider), ("user", KEY, "gpt-5-mini", "openai"))
        self.assertEqual(state, {"available": True, "needs_key": False, "paid_by": "user", "blocked": None, "locked": False})
        source, state = self.resolve("guide", "user_only")
        self.assertEqual((source, state["needs_key"], state["available"], state["locked"]), (None, True, True, False))

    def test_the_key_of_any_provider_pays(self):
        for provider, key in (("anthropic", ANTHROPIC_KEY), ("google", GOOGLE_KEY), ("openrouter", OPENROUTER_KEY)):
            source, _ = self.resolve("guide", "user_only", own=True, provider=provider, key=key)
            self.assertEqual((source.provider, source.api_key), (provider, key), provider)

    def test_a_locked_session_says_so_instead_of_asking_for_a_key_that_is_already_saved(self):
        source, state = self.resolve("guide", "user_only", own=True, locked=True)
        self.assertEqual((source, state["locked"], state["needs_key"], state["available"]), (None, True, False, True))

    def test_group_then_user_uses_the_groups_key_first_whether_or_not_they_have_their_own(self):
        for own in (False, True):
            source, state = self.resolve("chat", "group_then_user", own=own)
            self.assertEqual((source.key_source, source.api_key, state["paid_by"], state["blocked"]), ("group", "GROUPKEY", "group", None), own)

    def test_group_then_user_goes_on_with_their_own_when_the_group_has_none_and_needs_a_key_without_either(self):
        source, state = self.resolve("chat", "group_then_user", own=True, group=False)
        self.assertEqual((source.key_source, state["paid_by"]), ("user", "user"))
        source, state = self.resolve("chat", "group_then_user", group=False)
        self.assertEqual((source, state["needs_key"], state["available"]), (None, True, True))
        source, state = self.resolve("chat", "group_then_user", own=True, group=False, locked=True)
        self.assertEqual((source, state["locked"], state["needs_key"]), (None, True, False))

    def test_an_unknown_mode_stored_by_an_earlier_version_is_the_default_of_the_feature(self):
        with patched(**{"chat.key_source": "user_or_group", "guide.key_source": "everybody"}):
            self.assertEqual((ai_source.mode("chat"), ai_source.mode("guide")), ("group_then_user", "group_then_user"))

    def test_group_only_ignores_the_players_key_and_needs_none(self):
        source, state = self.resolve("guide", "group_only", own=True)
        self.assertEqual((source.key_source, state["needs_key"], state["locked"]), ("group", False, False))
        source, state = self.resolve("guide", "group_only", group=False)
        self.assertEqual((source, state["available"], state["needs_key"]), (None, False, False))

    def test_a_switched_off_feature_has_no_source_whoever_would_pay(self):
        for mode in ai_source.MODES:
            source, state = self.resolve("chat", mode, own=True, enabled=False)
            self.assertEqual((source, state), (None, {"available": False, "needs_key": False, "paid_by": None, "blocked": None, "locked": False}), mode)

    def test_the_defaults_are_the_groups_key_first_for_the_chat_and_the_guide(self):
        self.assertEqual(settings.REGISTRY["chat.key_source"].default, "group_then_user")
        self.assertEqual(settings.REGISTRY["guide.key_source"].default, "group_then_user")
        self.assertIsNone(settings.REGISTRY["chat.key_source"].check("group_only"))
        self.assertIsNotNone(settings.REGISTRY["chat.key_source"].check("everybody"))

    def test_the_source_never_shows_its_key_when_printed(self):
        self.assertNotIn(KEY, repr(ai_source.Source("user", "openai", KEY, "gpt-5")))


class WhichKeyTests(unittest.TestCase):
    """A player with several keys: their preference, then the provider the group uses for that feature, then the first they have."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.dek = ai_env.give_key(self.db, 1, KEY, "gpt-5-mini")
        user_ai.save(self.db, 1, self.dek, "anthropic", ANTHROPIC_KEY)
        user_ai.save(self.db, 1, self.dek, "google", GOOGLE_KEY)

    def source(self, use="chat", group="google", **settings_):
        with patched(**ai_env.group(group, "G", "m"), **settings_):
            return ai_source.own_source(self.db, 1, self.dek, use)

    def test_the_preferred_provider_comes_first(self):
        user_ai.set_preferred(self.db, 1, "anthropic")
        self.assertEqual(self.source().provider, "anthropic")

    def test_without_a_preference_the_provider_the_group_uses_for_that_feature_comes_next(self):
        self.assertEqual(self.source(group="google").provider, "google")
        self.assertEqual(self.source(group="anthropic").provider, "anthropic")

    def test_when_neither_applies_the_first_they_have_in_order(self):
        self.assertEqual(self.source(group="openrouter").provider, "openai")

    def test_a_preference_for_a_provider_they_no_longer_have_is_ignored(self):
        user_ai.set_preferred(self.db, 1, "openrouter")
        self.assertEqual(self.source(group="google").provider, "google")

    def test_a_key_that_does_not_open_is_skipped_for_the_next_one(self):
        user_ai.set_preferred(self.db, 1, "anthropic")
        self.db.get(models.UserAiKey, (1, "anthropic")).secret = "garbage"
        self.db.commit()
        self.assertEqual(self.source(group="openrouter").provider, "openai")

    def test_a_locked_session_has_no_source_at_all(self):
        with patched():
            self.assertIsNone(ai_source.own_source(self.db, 1, None, "chat"))

    def test_the_first_choice_without_a_feature_is_the_preference_then_the_order(self):
        with patched():
            self.assertEqual(ai_source.own_source(self.db, 1, self.dek).provider, "openai")
            user_ai.set_preferred(self.db, 1, "google")
            self.assertEqual(ai_source.own_source(self.db, 1, self.dek).provider, "google")


class LimitsTests(unittest.TestCase):
    def test_a_question_paid_with_the_players_own_key_only_has_the_per_minute_limit_and_the_group_is_not_counted(self):
        with patched():
            own = chat_limits.scopes_of(1, own_key=True)
            group = chat_limits.scopes_of(1)
            own_guide = guide_limits.scopes_of(1, own_key=True)
        self.assertEqual([(s.name, [w for w, _ in s.limits]) for s in own], [("user", [60])])
        self.assertEqual([s.name for s in group], ["user", "group"])
        self.assertEqual([(s.name, [w for w, _ in s.limits]) for s in own_guide], [("user", [60])])


class OwnKeyInAQuestionTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.user = self.db.get(models.User, 1)
        patcher = patched(**{"chat.prompt": "Eres un bot."})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = ai_source.Source("user", "openai", KEY, "gpt-5-mini")

    def reply(self, history, info):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "Hola"})])

    def test_the_question_is_recorded_as_paid_by_the_player_with_their_model_and_provider(self):
        chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(self.reply), source=ai_source.Source("user", "anthropic", ANTHROPIC_KEY, "claude-haiku-5-5"))
        (row,) = self.db.query(models.AiUsage).all()
        self.assertEqual((row.key_source, row.provider, row.model, row.user_id), ("user", "anthropic", "claude-haiku-5-5", 1))

    def test_the_model_is_built_with_the_players_key_and_model(self):
        built = []
        with mock.patch.object(chat_agent.ai_build, "model_for", side_effect=lambda use, source=None: built.append(source) or FunctionModel(self.reply)):
            chat_agent.ask(self.db, self.user, "hola", [], source=self.source)
        self.assertEqual(built, [self.source])

    def test_their_key_never_reaches_the_error(self):
        def fail(history, info):
            raise RuntimeError(f"401 incorrect key {KEY}")

        with self.assertRaises(AIError) as error:
            chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(fail), source=self.source)
        self.assertNotIn(KEY, str(error.exception))
        self.assertIn("***", str(error.exception))

    def test_their_own_quota_is_not_an_event_for_the_admins(self):
        quota = Quota(kind="billing")
        error = type("Rate", (Exception,), {})()
        with mock.patch.object(chat_agent, "classify", return_value=quota), mock.patch.object(chat_agent.ai_quota, "report") as report:
            chat_agent.failure(error, "chat", key=KEY)
            self.assertFalse(report.called)
            chat_agent.failure(error, "chat")
            self.assertTrue(report.called)


class OwnKeyMessagesTests(unittest.TestCase):
    own = ai_source.Source("user", "openai", KEY, "gpt-5")
    group = ai_source.Source("group", "openai", "GROUPKEY", "gpt-5")

    def test_a_player_is_told_it_is_their_key_that_has_no_balance_or_was_refused(self):
        quota = chat_router.own_key_detail(self.own, QuotaError("q", Quota(kind="billing", retry_after=None)))
        denied = chat_router.own_key_detail(self.own, ProviderError("x", failure.DENIED))
        self.assertEqual(quota, messages.USER_KEY_QUOTA.format(when=""))
        self.assertEqual(denied, messages.USER_KEY_DENIED)
        self.assertIn("tu clave", quota.lower())

    def test_the_groups_key_and_other_failures_keep_their_usual_answers(self):
        self.assertIsNone(chat_router.own_key_detail(self.group, ProviderError("x", failure.DENIED)))
        self.assertIsNone(chat_router.own_key_detail(self.own, ProviderError("x", failure.TIMEOUT)))
        self.assertIsNone(chat_router.own_key_detail(None, AIError("x")))


class ModelsTests(unittest.TestCase):
    def test_only_chat_models_without_dated_copies_are_offered_for_openai(self):
        ids = ["gpt-4.1", "gpt-4.1-2025-04-14", "gpt-4.1-mini", "text-embedding-3-small", "gpt-4o-mini-transcribe", "gpt-image-1",
               "o3", "whisper-1", "gpt-4o-realtime-preview", "chatgpt-4o-latest"]
        self.assertEqual(ai_models.for_chat(ids), ["chatgpt-4o-latest", "gpt-4.1", "gpt-4.1-mini", "o3"])

    def test_the_other_providers_lists_are_offered_as_they_come_without_what_cannot_be_a_model_name(self):
        self.assertEqual(ai_models.for_chat(["claude-haiku-5-5", "claude-sonnet-5-5"], "anthropic"), ["claude-haiku-5-5", "claude-sonnet-5-5"])
        self.assertEqual(ai_models.for_chat(["openai/gpt-4.1-mini", "bad name", "~openai/gpt-latest"], "openrouter"), ["openai/gpt-4.1-mini", "~openai/gpt-latest"])

    def test_each_model_has_its_tier_from_what_it_costs(self):
        by_id = {m["id"]: m for m in ai_models.describe(["gpt-5-nano", "gpt-4.1", "chatgpt-4o-latest", "gpt-9-unknown"])}
        self.assertEqual(by_id["gpt-5-nano"]["tier"], "economico")
        self.assertEqual(by_id["gpt-4.1"]["tier"], "medio")
        self.assertEqual(by_id["chatgpt-4o-latest"]["tier"], "caro")
        self.assertEqual((by_id["gpt-9-unknown"]["tier"], by_id["gpt-9-unknown"]["output_per_million"]), ("sin_precio", None))
        self.assertGreater(by_id["gpt-4.1"]["output_per_million"], by_id["gpt-4.1"]["input_per_million"])

    def test_the_prices_of_another_provider_are_read_for_that_provider(self):
        found = ai_models.describe(["claude-haiku-5-5", "claude-unknown-9"], "anthropic")
        self.assertEqual([m["id"] for m in found], ["claude-haiku-5-5", "claude-unknown-9"])
        self.assertIsNone(found[1]["output_per_million"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session(threads=True)
        seed(self.db)
        ai_env.free_wallet(self.db)
        for user in self.db.query(models.User).all():
            user.password = hashpw(PASSWORD.encode(), gensalt(4)).decode()
        self.db.commit()
        route.limiter.clear()
        self.addCleanup(route.limiter.clear)
        route.UNLOCK_BY_ACCOUNT.reset("1")
        self.addCleanup(route.UNLOCK_BY_ACCOUNT.reset, "1")
        self.dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini")  # the player is unlocked and has an OpenAI key unless a test says otherwise
        app = FastAPI()
        app.include_router(route.router)
        self.user = self.db.get(models.User, 1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[auth.get_unlock] = lambda: self.dek
        app.dependency_overrides[route.get_db] = lambda: self.db
        self.client = TestClient(app)
        for patcher in (patched(), mock.patch.object(route.audit, "record_event"), mock.patch.object(ai_vault, "KDF", ai_env.FAST_KDF)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def put(self, provider="openai", **body):
        return self.client.put(f"/users/ana/ai/{provider}", json=body)

    def test_a_valid_key_is_checked_with_its_provider_saved_and_never_returned(self):
        with mock.patch.object(route.model_list, "list_models", return_value=["claude-haiku-5-5"]) as listed:
            response = self.put("anthropic", api_key=f" {ANTHROPIC_KEY} ")
        listed.assert_called_once_with("anthropic", ANTHROPIC_KEY)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["keys"]["anthropic"]["has_key"], body["keys"]["anthropic"]["hint"], body["keys"]["anthropic"]["model"]), (True, "6789", user_ai.DEFAULT_MODELS["anthropic"]))
        self.assertNotIn(ANTHROPIC_KEY, response.text)
        self.assertEqual(user_ai.credentials(self.db, 1, self.dek, "anthropic"), (ANTHROPIC_KEY, user_ai.DEFAULT_MODELS["anthropic"]))

    def test_every_provider_takes_its_own_kind_of_key_and_refuses_another_provider_s_without_calling_anybody(self):
        good = {"openai": KEY, "anthropic": ANTHROPIC_KEY, "openrouter": OPENROUTER_KEY, "google": GOOGLE_KEY}
        with mock.patch.object(route.model_list, "list_models", return_value=[]) as listed:
            for provider, key in good.items():
                self.assertEqual(self.put(provider, api_key=key).status_code, 200, provider)
            self.assertEqual(listed.call_count, 4)
            listed.reset_mock()
            self.assertEqual(self.put("openai", api_key=ANTHROPIC_KEY).status_code, 400)
            self.assertEqual(self.put("anthropic", api_key=KEY).status_code, 400)
            self.assertEqual(self.put("google", api_key="hello").status_code, 400)
            self.assertIn("Anthropic", self.put("anthropic", api_key="nope").json()["detail"])
        self.assertFalse(listed.called)

    def test_an_unknown_provider_is_not_a_route(self):
        self.assertEqual(self.client.put("/users/ana/ai/nobody", json={"api_key": KEY}).status_code, 422)
        self.assertEqual(self.client.get("/users/ana/ai/nobody/models").status_code, 422)

    def test_saving_needs_the_keys_unlocked_and_says_so_with_a_423_and_touches_nothing(self):
        self.dek = None
        with mock.patch.object(route.model_list, "list_models") as listed:
            response = self.put(api_key=OTHER_KEY)
        self.assertEqual((response.status_code, response.json()["detail"]), (423, messages.USER_AI_LOCKED))
        self.assertFalse(listed.called)
        self.dek = ai_vault_dek = None
        del ai_vault_dek
        self.assertEqual(self.db.query(models.UserAiKey).count(), 1)

    def test_the_status_never_carries_the_key_and_says_who_pays_for_each_feature(self):
        response = self.client.get("/users/ana/ai")
        self.assertNotIn(KEY, response.text)
        body = response.json()
        self.assertEqual((body["locked"], body["keys"]["openai"]["hint"], body["preferred"]), (False, "6789", None))
        self.assertEqual((body["chat"]["paid_by"], body["chat"]["mode"]), ("group", "group_then_user"))  # the group's first
        self.assertEqual((body["guide"]["paid_by"], body["guide"]["mode"]), ("group", "group_then_user"))
        self.assertEqual(set(body["keys"]), set(user_ai.PROVIDERS))
        self.assertEqual(body["default_models"], user_ai.DEFAULT_MODELS)

    def test_a_locked_session_sees_that_there_are_keys_and_none_of_their_details(self):
        self.dek = None
        body = self.client.get("/users/ana/ai").json()
        self.assertEqual((body["locked"], body["keys"]["openai"]["has_key"], body["keys"]["openai"]["hint"]), (True, True, None))
        self.assertEqual((body["guide"]["locked"], body["guide"]["needs_key"]), (False, False))  # the group's key answers it
        with patched(**{"guide.key_source": "user_only"}):
            body = self.client.get("/users/ana/ai").json()
        self.assertEqual((body["guide"]["locked"], body["guide"]["needs_key"]), (True, False))

    def test_what_is_not_a_key_is_refused_without_calling_the_provider(self):
        with mock.patch.object(route.model_list, "list_models") as listed:
            for bad in ("hello", "sk-x", ""):
                self.assertEqual(self.put(api_key=bad).status_code, 400, bad)
        self.assertFalse(listed.called)

    def test_a_key_the_provider_refuses_is_not_saved_and_the_message_names_it_and_does_not_repeat_the_key(self):
        with mock.patch.object(route.model_list, "list_models", side_effect=ProviderError(f"google: 401 {GOOGLE_KEY}", failure.DENIED)):
            response = self.put("google", api_key=GOOGLE_KEY)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], messages.USER_AI_KEY_REJECTED.format(provider="Google", where=route.WHERE_TO_MAKE_IT["google"]))
        self.assertNotIn(GOOGLE_KEY, response.text)
        self.assertEqual(user_ai.providers_with_key(self.db, 1), ["openai"])

    def test_a_key_without_balance_says_so_and_provider_trouble_is_a_bad_gateway(self):
        with mock.patch.object(route.model_list, "list_models", side_effect=QuotaError("q", Quota(kind="billing"))):
            self.assertEqual(self.put(api_key=OTHER_KEY).status_code, 429)
        with mock.patch.object(route.model_list, "list_models", side_effect=AIError("boom")):
            self.assertEqual(self.put(api_key=OTHER_KEY).status_code, 502)

    def test_a_new_key_without_a_model_keeps_the_one_they_chose_and_a_model_sent_with_it_wins(self):
        user_ai.set_model(self.db, 1, "openai", "gpt-5")
        with mock.patch.object(route.model_list, "list_models", return_value=[]):
            body = self.put(api_key=OTHER_KEY).json()
            self.assertEqual((body["keys"]["openai"]["hint"], body["keys"]["openai"]["model"]), ("3210", "gpt-5"))
            self.assertEqual(self.put(api_key=KEY, model="o3").json()["keys"]["openai"]["model"], "o3")

    def test_the_model_can_be_changed_without_sending_the_key_again_even_while_locked(self):
        body = self.put(model="gpt-5").json()
        self.assertEqual(body["keys"]["openai"]["model"], "gpt-5")
        self.dek = None
        self.assertEqual(self.put(model="gpt-4.1").status_code, 200, "it touches no secret")
        self.assertEqual(self.put("google", model="gemini-x").status_code, 409, "no key for that provider")
        self.assertEqual(self.put(model="not a model").status_code, 400)
        self.assertEqual(self.put().status_code, 400, "a key or a model: something to change")

    def test_a_key_can_be_taken_away_without_unlocking_and_the_others_stay(self):
        with mock.patch.object(route.model_list, "list_models", return_value=[]):
            self.put("google", api_key=GOOGLE_KEY)
        self.dek = None
        body = self.client.delete("/users/ana/ai/openai").json()
        self.assertEqual((body["keys"]["openai"]["has_key"], body["keys"]["google"]["has_key"]), (False, True))

    def test_nobody_else_can_touch_them_not_even_an_admin(self):
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        self.assertEqual(self.client.get("/users/beto/ai").status_code, 403)
        self.assertEqual(self.client.put("/users/beto/ai/openai", json={"api_key": KEY}).status_code, 403)
        self.assertEqual(self.client.delete("/users/beto/ai/openai").status_code, 403)
        self.assertEqual(self.client.post("/users/beto/ai/unlock", json={"password": PASSWORD}).status_code, 403)
        self.user = types.SimpleNamespace(id=3, username="root", name="Root", is_admin=1, is_active=1)
        for path in ("/users/ana/ai", "/users/ana/ai/usage", "/users/ana/ai/openai/models"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_the_models_are_those_of_the_provider_of_the_key_with_their_tiers(self):
        with mock.patch.object(route.model_list, "list_models", return_value=["gpt-4.1-mini", "gpt-5-nano", "text-embedding-3-small"]) as listed:
            body = self.client.get("/users/ana/ai/openai/models").json()
        listed.assert_called_once_with("openai", KEY)
        self.assertEqual([m["id"] for m in body["models"]], ["gpt-4.1-mini", "gpt-5-nano"])
        self.assertEqual(body["current"], "gpt-4.1-mini")

    def test_without_a_key_for_that_provider_there_is_nothing_to_list_or_try_and_a_locked_session_is_told_to_unlock(self):
        with mock.patch.object(route.model_list, "list_models") as listed:
            self.assertEqual(self.client.get("/users/ana/ai/google/models").status_code, 409)
            self.dek = None
            self.assertEqual(self.client.get("/users/ana/ai/openai/models").status_code, 423)
            self.assertEqual(self.client.post("/users/ana/ai/openai/test").status_code, 423)
        self.assertFalse(listed.called)

    def test_the_test_asks_the_guide_question_with_their_key_model_and_provider(self):
        with mock.patch.object(route.guide_agent, "probe", return_value="Hola") as probe:
            body = self.client.post("/users/ana/ai/openai/test").json()
        source = probe.call_args.kwargs["source"]
        self.assertEqual((source.key_source, source.provider, source.api_key, source.model, probe.call_args.kwargs["user_id"]), ("user", "openai", KEY, "gpt-4.1-mini", 1))
        self.assertEqual(body, {"reply": "Hola", "model": "gpt-4.1-mini", "provider": "openai"})
        with mock.patch.object(route.guide_agent, "probe", side_effect=QuotaError("q", Quota(kind="billing"))):
            self.assertEqual(self.client.post("/users/ana/ai/openai/test").status_code, 429)

    def test_checking_and_trying_keys_is_limited_so_the_server_is_no_key_tester(self):
        with mock.patch.object(route.model_list, "list_models", side_effect=ProviderError("x", failure.DENIED)):
            saves = [self.put(api_key=OTHER_KEY).status_code for _ in range(route.CHANGES_PER_HOUR + 1)]
        self.assertEqual((saves[:-1], saves[-1]), ([400] * route.CHANGES_PER_HOUR, 429))

    def test_listing_has_a_limit_of_its_own_and_saving_still_has_its_own(self):
        with mock.patch.object(route.model_list, "list_models", return_value=[]):
            codes = [self.client.get("/users/ana/ai/openai/models").status_code for _ in range(route.LISTINGS_PER_HOUR + 1)]
            self.assertEqual((codes[:-1] == [200] * route.LISTINGS_PER_HOUR, codes[-1]), (True, 429))
            self.assertEqual(self.put(api_key=OTHER_KEY).status_code, 200)

    def test_the_preferred_provider_is_one_they_have_a_key_for_and_null_goes_back_to_the_app_picking(self):
        with mock.patch.object(route.model_list, "list_models", return_value=[]):
            self.put("google", api_key=GOOGLE_KEY)
        response = self.client.put("/users/ana/ai/preferred", json={"provider": "google"})
        self.assertEqual((response.status_code, response.json()["preferred"]), (200, "google"))
        self.assertEqual(self.client.put("/users/ana/ai/preferred", json={"provider": "anthropic"}).status_code, 409, "no key for it")
        self.assertEqual(self.client.put("/users/ana/ai/preferred", json={"provider": "nobody"}).status_code, 422)
        self.assertIsNone(self.client.put("/users/ana/ai/preferred", json={"provider": None}).json()["preferred"])


class UnlockRouteTests(unittest.TestCase):
    """The password opens the keys of a session: a new token that carries the data key."""

    def setUp(self):
        self.db = make_session(threads=True)
        seed(self.db)
        ai_env.free_wallet(self.db)
        for user in self.db.query(models.User).all():
            user.password = hashpw(PASSWORD.encode(), gensalt(4)).decode()
        self.db.commit()
        route.UNLOCK_BY_ACCOUNT.reset("1")
        self.addCleanup(route.UNLOCK_BY_ACCOUNT.reset, "1")
        app = FastAPI()
        app.include_router(route.router)
        self.user = self.db.get(models.User, 1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[route.get_db] = lambda: self.db
        self.client = TestClient(app)
        for patcher in (patched(), mock.patch.object(route.audit, "record_event") , mock.patch.object(ai_vault, "KDF", ai_env.FAST_KDF)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def unlock(self, password=PASSWORD):
        return self.client.post("/users/ana/ai/unlock", json={"password": password})

    def claim_of(self, response):
        return jwt.decode(response.json()["access_token"], auth.config.SECRET_KEY, algorithms=[auth.ALGORITHM]).get("ku")

    def test_the_right_password_makes_the_vault_and_answers_a_token_that_carries_the_data_key(self):
        response = self.unlock()
        self.assertEqual(response.status_code, 200)
        claim = self.claim_of(response)
        dek = ai_vault.open_claim(1, claim, 3600)
        self.assertIsNotNone(dek)
        self.assertEqual(user_ai.unlock(self.db, 1, PASSWORD), dek, "the one of the vault")
        self.assertEqual(response.json()["token_type"], "bearer")
        self.assertFalse(response.json()["locked"])
        self.assertNotIn(ai_vault._b64(dek), response.text, "the data key itself never leaves the server")

    def test_the_token_still_names_the_account_and_dies_with_a_password_change(self):
        payload = jwt.decode(self.unlock().json()["access_token"], auth.config.SECRET_KEY, algorithms=[auth.ALGORITHM])
        self.assertEqual((payload["username"], payload["pwv"]), ("ana", auth.password_fingerprint(self.user)))

    def test_a_wrong_password_opens_nothing_makes_nothing_and_is_counted(self):
        response = self.unlock("not the password")
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.PASSWORD_WRONG))
        self.assertEqual(self.db.query(models.UserAiVault).count(), 0)
        self.assertEqual(route.audit.record_event.call_args.args[1], "ai_unlock_failed")

    def test_guessing_the_password_here_is_stopped_like_at_the_login(self):
        codes = [self.unlock("nope").status_code for _ in range(6)]
        self.assertEqual(codes, [400] * 5 + [429])
        self.assertEqual(self.unlock(PASSWORD).status_code, 429, "even the right one waits")


if __name__ == "__main__":
    unittest.main()

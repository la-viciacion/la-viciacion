"""A player's own AI key: how it is kept (encrypted, bound to the player, never returned), whose key pays for each question, what
the player is told when their own key is the one that fails, and the routes that save, change, try and remove it."""
import types
import unittest
from unittest import mock

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
from src.utils import ai_ledger, ai_models, ai_source, messages, settings, user_ai
from tests.sqlite_db import make_session
from tests.test_chat import seed

KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
OTHER_KEY = "sk-proj-ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"


def values(**overrides):
    base = {key: spec.default for key, spec in settings.REGISTRY.items()}
    return {**base, "ai.api_key": "GROUPKEY", "ai.provider": "openai", "ai.model": "gpt-4.1-mini", "chat.model": None, **overrides}


def patched(**overrides):
    table = values(**overrides)
    return mock.patch.object(settings, "get", side_effect=lambda key: table[key])


class KeyStorageTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def test_what_is_stored_is_not_the_key_and_opens_only_for_its_player(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        stored = self.db.get(models.UserSettings, 1).ai_api_key
        self.assertNotIn(KEY, stored)
        self.assertNotIn("sk-", stored)
        self.assertEqual(user_ai.unseal(1, stored), KEY)
        self.assertIsNone(user_ai.unseal(2, stored), "copied into another player's row it does not open")

    def test_a_different_secret_key_cannot_open_it_and_the_player_is_asked_for_it_again(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        with mock.patch.object(user_ai.config, "SECRET_KEY", "another-secret"):
            self.assertIsNone(user_ai.credentials(self.db, 1))
            status = user_ai.status(self.db, 1)
        self.assertEqual((status["has_key"], status["unreadable"]), (False, True))
        self.assertIsNone(status["hint"])

    def test_the_status_shows_the_last_characters_and_never_the_key(self):
        user_ai.save(self.db, 1, KEY, "gpt-5-mini")
        status = user_ai.status(self.db, 1)
        self.assertEqual((status["has_key"], status["hint"], status["model"], status["provider"]), (True, "6789", "gpt-5-mini", "openai"))
        self.assertNotIn(KEY, str(status))

    def test_removing_it_clears_all_three_columns_and_a_player_without_row_has_none(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        user_ai.clear(self.db, 1)
        row = self.db.get(models.UserSettings, 1)
        self.assertEqual((row.ai_api_key, row.ai_key_hint, row.ai_model), (None, None, None))
        self.assertFalse(user_ai.status(self.db, 2)["has_key"])
        user_ai.clear(self.db, 2)

    def test_the_model_can_change_only_when_there_is_a_key(self):
        self.assertFalse(user_ai.set_model(self.db, 1, "gpt-5"))
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        self.assertTrue(user_ai.set_model(self.db, 1, "gpt-5"))
        self.assertEqual(user_ai.credentials(self.db, 1), (KEY, "gpt-5"))

    def test_only_what_looks_like_an_openai_key_and_a_model_name_is_accepted(self):
        self.assertEqual(user_ai.clean_key(f"  {KEY} "), KEY)
        for bad in ("", None, "sk-short", "hello", "sk- with spaces and more text here", "AIzaSyFakeGoogleKey0123456789"):
            self.assertIsNone(user_ai.clean_key(bad), bad)
        self.assertEqual(user_ai.clean_model(" gpt-4.1-mini "), "gpt-4.1-mini")
        for bad in ("", None, "a b", "x" * 65, "-gpt", "gpt;drop"):
            self.assertIsNone(user_ai.clean_model(bad), bad)

    def test_the_encrypted_column_is_not_loaded_with_the_row(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        self.db.expire_all()
        row = self.db.get(models.UserSettings, 1)
        self.assertNotIn("ai_api_key", row.__dict__)

    def test_it_is_not_part_of_what_a_player_can_patch_nor_of_their_preferences(self):
        from src.database import schemas

        self.assertNotIn("ai_api_key", schemas.UserSettingsUpdate.model_fields)
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        from src.utils import user_settings

        self.assertNotIn(KEY, str(user_settings.get(self.db, 1)))
        self.assertNotIn("ai_api_key", user_settings.get(self.db, 1))


class WhoPaysTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def resolve(self, feature, mode, own=False, group=True, enabled=True):
        if own:
            user_ai.save(self.db, 1, KEY, "gpt-5-mini")
        else:
            user_ai.clear(self.db, 1)
        key = "GROUPKEY" if group else None
        with patched(**{f"{feature}.key_source": mode, f"{feature}.enabled": enabled, "ai.api_key": key}):
            return ai_source.resolve(self.db, 1, feature), ai_source.availability(self.db, 1, feature)

    def test_user_only_uses_the_players_key_and_nothing_else(self):
        source, state = self.resolve("guide", "user_only", own=True)
        self.assertEqual((source.key_source, source.api_key, source.model, source.provider), ("user", KEY, "gpt-5-mini", "openai"))
        self.assertEqual(state, {"available": True, "needs_key": False, "paid_by": "user", "blocked": None})
        source, state = self.resolve("guide", "user_only")
        self.assertEqual((source, state["needs_key"], state["available"]), (None, True, True))

    def test_user_or_group_prefers_their_own_and_falls_back_to_the_groups(self):
        self.assertEqual(self.resolve("chat", "user_or_group", own=True)[0].key_source, "user")
        db_source, state = self.resolve("chat", "user_or_group", own=False)
        self.assertEqual((db_source.key_source, db_source.api_key, state["paid_by"]), ("group", "GROUPKEY", "group"))

    def test_user_or_group_with_neither_needs_a_key(self):
        source, state = self.resolve("chat", "user_or_group", group=False)
        self.assertEqual((source, state["needs_key"], state["available"]), (None, True, True))

    def test_group_only_ignores_the_players_key_and_needs_none(self):
        source, state = self.resolve("guide", "group_only", own=True)
        self.assertEqual((source.key_source, state["needs_key"]), ("group", False))
        source, state = self.resolve("guide", "group_only", group=False)
        self.assertEqual((source, state["available"], state["needs_key"]), (None, False, False))

    def test_a_switched_off_feature_has_no_source_whoever_would_pay(self):
        for mode in ai_source.MODES:
            source, state = self.resolve("chat", mode, own=True, enabled=False)
            self.assertEqual((source, state), (None, {"available": False, "needs_key": False, "paid_by": None, "blocked": None}), mode)

    def test_the_defaults_are_the_chat_for_the_group_and_the_guide_for_the_player(self):
        self.assertEqual(settings.REGISTRY["chat.key_source"].default, "user_or_group")
        self.assertEqual(settings.REGISTRY["guide.key_source"].default, "user_only")
        self.assertIsNone(settings.REGISTRY["chat.key_source"].check("group_only"))
        self.assertIsNotNone(settings.REGISTRY["chat.key_source"].check("everybody"))

    def test_the_source_never_shows_its_key_when_printed(self):
        self.assertNotIn(KEY, repr(ai_source.Source("user", "openai", KEY, "gpt-5")))


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
        self.user = self.db.get(models.User, 1)
        patcher = patched(**{"chat.prompt": "Eres un bot."})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = ai_source.Source("user", "openai", KEY, "gpt-5-mini")

    def reply(self, history, info):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "Hola"})])

    def test_the_question_is_recorded_as_paid_by_the_player_with_their_model(self):
        chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(self.reply), source=self.source)
        (row,) = self.db.query(models.AiUsage).all()
        self.assertEqual((row.key_source, row.provider, row.model, row.user_id), ("user", "openai", "gpt-5-mini", 1))

    def test_the_model_is_built_with_the_players_key_and_model(self):
        built = []
        with mock.patch.object(chat_agent.chat_model, "build_model", side_effect=lambda source=None: built.append(source) or FunctionModel(self.reply)):
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
    def test_only_chat_models_without_dated_copies_are_offered(self):
        ids = ["gpt-4.1", "gpt-4.1-2025-04-14", "gpt-4.1-mini", "text-embedding-3-small", "gpt-4o-mini-transcribe", "gpt-image-1",
               "o3", "whisper-1", "gpt-4o-realtime-preview", "chatgpt-4o-latest"]
        self.assertEqual(ai_models.for_chat(ids), ["chatgpt-4o-latest", "gpt-4.1", "gpt-4.1-mini", "o3"])

    def test_each_model_has_its_tier_from_what_it_costs(self):
        by_id = {m["id"]: m for m in ai_models.describe(["gpt-5-nano", "gpt-4.1", "chatgpt-4o-latest", "gpt-9-unknown"])}
        self.assertEqual(by_id["gpt-5-nano"]["tier"], "economico")
        self.assertEqual(by_id["gpt-4.1"]["tier"], "medio")
        self.assertEqual(by_id["chatgpt-4o-latest"]["tier"], "caro")
        self.assertEqual((by_id["gpt-9-unknown"]["tier"], by_id["gpt-9-unknown"]["output_per_million"]), ("sin_precio", None))
        self.assertGreater(by_id["gpt-4.1"]["output_per_million"], by_id["gpt-4.1"]["input_per_million"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session(threads=True)
        seed(self.db)
        route.limiter.clear()
        self.addCleanup(route.limiter.clear)
        app = FastAPI()
        app.include_router(route.router)
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[route.get_db] = lambda: self.db
        self.client = TestClient(app)
        patcher = patched()
        patcher.start()
        self.addCleanup(patcher.stop)

    def put(self, **body):
        return self.client.put("/users/ana/ai", json=body)

    def test_a_valid_key_is_checked_with_openai_saved_and_never_returned(self):
        with mock.patch.object(route.open_ai, "list_models", return_value=["gpt-4.1-mini"]) as listed:
            response = self.put(api_key=f" {KEY} ")
        listed.assert_called_once_with(KEY)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["has_key"], body["hint"], body["model"]), (True, "6789", route.DEFAULT_MODEL))
        self.assertNotIn(KEY, response.text)
        self.assertEqual(user_ai.credentials(self.db, 1), (KEY, route.DEFAULT_MODEL))

    def test_the_status_never_carries_the_key_and_says_who_pays_for_each_feature(self):
        user_ai.save(self.db, 1, KEY, "gpt-5-mini")
        response = self.client.get("/users/ana/ai")
        self.assertNotIn(KEY, response.text)
        body = response.json()
        self.assertEqual(body["key"]["hint"], "6789")
        self.assertEqual((body["chat"]["paid_by"], body["chat"]["mode"]), ("user", "user_or_group"))
        self.assertEqual((body["guide"]["paid_by"], body["guide"]["mode"]), ("user", "user_only"))

    def test_what_is_not_a_key_is_refused_without_calling_openai(self):
        with mock.patch.object(route.open_ai, "list_models") as listed:
            for bad in ("hello", "sk-x", ""):
                self.assertEqual(self.put(api_key=bad).status_code, 400, bad)
        self.assertFalse(listed.called)
        self.assertFalse(user_ai.status(self.db, 1)["has_key"])

    def test_a_key_that_openai_refuses_is_not_saved_and_the_message_does_not_repeat_it(self):
        with mock.patch.object(route.open_ai, "list_models", side_effect=ProviderError(f"openai: 401 {KEY}", failure.DENIED)):
            response = self.put(api_key=KEY)
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.USER_AI_KEY_REJECTED))
        self.assertNotIn(KEY, response.text)
        self.assertFalse(user_ai.status(self.db, 1)["has_key"])

    def test_a_key_without_balance_says_so_and_openai_trouble_is_a_bad_gateway(self):
        with mock.patch.object(route.open_ai, "list_models", side_effect=QuotaError("q", Quota(kind="billing"))):
            self.assertEqual(self.put(api_key=KEY).status_code, 429)
        with mock.patch.object(route.open_ai, "list_models", side_effect=AIError("boom")):
            self.assertEqual(self.put(api_key=KEY).status_code, 502)

    def test_the_model_can_be_changed_without_sending_the_key_again(self):
        self.assertEqual(self.put(model="gpt-5").status_code, 409)  # nothing to change yet
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        self.assertEqual(self.put(model="gpt-5").json()["model"], "gpt-5")
        self.assertEqual(self.put(model="not a model").status_code, 400)
        self.assertEqual(user_ai.credentials(self.db, 1), (KEY, "gpt-5"))

    def test_the_key_can_be_taken_away(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        response = self.client.delete("/users/ana/ai")
        self.assertEqual((response.status_code, response.json()["has_key"]), (200, False))
        self.assertIsNone(user_ai.credentials(self.db, 1))

    def test_nobody_else_can_touch_it_not_even_an_admin(self):
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        self.user.username, self.user.is_admin = "root", 1
        for response in (self.client.get("/users/ana/ai"), self.put(api_key=OTHER_KEY), self.client.delete("/users/ana/ai"),
                         self.client.get("/users/ana/ai/models"), self.client.post("/users/ana/ai/test")):
            self.assertEqual(response.status_code, 403)
        self.user.username = "ana"
        self.assertEqual(user_ai.credentials(self.db, 1), (KEY, "gpt-4.1-mini"))

    def test_the_models_are_those_of_their_key_with_their_tiers(self):
        self.assertEqual(self.client.get("/users/ana/ai/models").status_code, 409)
        user_ai.save(self.db, 1, KEY, "gpt-4.1-mini")
        with mock.patch.object(route.open_ai, "list_models", return_value=["gpt-4.1-mini", "gpt-5-nano", "text-embedding-3-small"]):
            body = self.client.get("/users/ana/ai/models").json()
        self.assertEqual([m["id"] for m in body["models"]], ["gpt-4.1-mini", "gpt-5-nano"])
        self.assertEqual(body["current"], "gpt-4.1-mini")

    def test_the_test_asks_the_guide_question_with_their_key_and_model(self):
        self.assertEqual(self.client.post("/users/ana/ai/test").status_code, 409)
        user_ai.save(self.db, 1, KEY, "gpt-5-mini")
        with mock.patch.object(route.guide_agent, "probe", return_value="Team Cherry") as probe:
            response = self.client.post("/users/ana/ai/test")
        self.assertEqual(response.json(), {"reply": "Team Cherry", "model": "gpt-5-mini"})
        source = probe.call_args.kwargs["source"]
        self.assertEqual((source.api_key, source.model, source.key_source), (KEY, "gpt-5-mini", "user"))

    def test_checking_and_trying_keys_is_limited_so_the_server_is_no_key_tester(self):
        with mock.patch.object(route.open_ai, "list_models", side_effect=ProviderError("x", failure.DENIED)):
            codes = [self.put(api_key=OTHER_KEY).status_code for _ in range(route.CHANGES_PER_HOUR + 1)]
        self.assertEqual(codes[:-1], [400] * route.CHANGES_PER_HOUR)
        self.assertEqual(codes[-1], 429)


class RecordedAsOwnTests(unittest.TestCase):
    def test_the_ledger_knows_the_two_sources(self):
        self.assertEqual((ai_ledger.GROUP, ai_ledger.USER), ("group", "user"))


if __name__ == "__main__":
    unittest.main()

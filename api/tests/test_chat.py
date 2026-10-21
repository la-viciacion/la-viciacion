"""The chat: what the agent may look up, how it is limited and what the endpoint refuses. The model is scripted
(FunctionModel), so no provider is called."""
import datetime
import os
import types
import unittest
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src import auth
from src.chat import limits as chat_limits
from src.chat import agent, tools
from src.chat import prompt as chat_prompt
from src.chat import model as chat_model
from src.clients.ai_error import AIError
from src.database import models
from src.routers import chat as chat_router
from src.routers.manage import system
from src.utils import ai_prompts, messages, settings
from tests.sqlite_db import make_session

START = datetime.datetime(2026, 3, 1, 10, 0)


def seed(db):
    db.add_all([
        models.User(id=1, name="Ana", username="ana", is_active=1, is_admin=0),
        models.User(id=2, name="Beto", username="beto", is_active=1, is_admin=0),
        models.User(id=3, name="Admin", username=models.GOD_USERNAME, is_active=1, is_admin=1),
        models.Game(id="g1", name="Hollow Knight", genres="Action, Platformer", tags="Horror, Singleplayer", avg_time=2 * 3600 * 10),
        models.Game(id="g2", name="Hollow Hunt", genres="Action"),
        models.Game(id="g3", name="Stardew Valley", genres="Simulation"),
    ])
    db.add_all([
        models.UserGame(user_id=1, game_id="g1", started_date=datetime.date(2026, 3, 1)),
        models.UserGame(user_id=2, game_id="g1", started_date=datetime.date(2026, 3, 1)),
        models.GameTimer(user_id=1, game_id="g1", start_time=START, end_time=START + datetime.timedelta(hours=3), duration_seconds=3 * 3600, is_active=False),
        models.GameTimer(user_id=2, game_id="g1", start_time=START, end_time=START + datetime.timedelta(hours=1), duration_seconds=3600, is_active=False),
    ])
    db.commit()


def deps(db):
    return types.SimpleNamespace(deps=tools.ChatDeps(db=db, user=db.get(models.User, 1)))


def scripted(*steps):
    """A model that answers each request with the next step: a ('tool', name, args) call or a final Reply."""
    queue = list(steps)

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        kind, *rest = queue.pop(0)
        if kind == "tool":
            return ModelResponse(parts=[ToolCallPart(tool_name=rest[0], args=rest[1])])
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=rest[0])])

    return FunctionModel(respond)


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def run_tool(self, tool, *args, **kwargs):
        import asyncio

        return asyncio.run(tool(deps(self.db), *args, **kwargs))

    def test_hours_are_given_in_hours_with_one_decimal(self):
        self.assertEqual(tools.hours(5400), 1.5)
        self.assertEqual(tools.hours(None), 0.0)

    def test_the_hours_ranking_puts_the_most_first_and_leaves_out_the_emergency_account(self):
        rows = self.run_tool(tools.ranking, "hours", 2026)
        self.assertEqual(rows, [{"name": "Ana", "hours": 3.0}, {"name": "Beto", "hours": 1.0}])

    def test_a_future_season_is_refused_so_the_model_corrects_itself(self):
        with self.assertRaises(ModelRetry):
            self.run_tool(tools.ranking, "hours", datetime.date.today().year + 1)

    def test_only_the_hours_ranking_covers_every_season(self):
        with self.assertRaises(ModelRetry):
            self.run_tool(tools.ranking, "achievements", 0)

    def test_a_game_is_found_by_part_of_its_name_but_an_ambiguous_one_lists_the_options(self):
        self.assertEqual(tools.find_game(self.db, "stardew").id, "g3")
        with self.assertRaises(ModelRetry) as error:
            tools.find_game(self.db, "hollow")
        self.assertIn("Hollow Knight", str(error.exception))
        self.assertIn("Hollow Hunt", str(error.exception))
        self.assertEqual(tools.find_game(self.db, "Hollow Hunt").id, "g2")  # the exact name wins

    def test_an_unknown_player_lists_who_there_is_and_never_the_emergency_account(self):
        with self.assertRaises(ModelRetry) as error:
            tools.find_player(self.db, "zoe")
        self.assertIn("Ana", str(error.exception))
        self.assertNotIn("Admin", str(error.exception))
        self.assertEqual(tools.find_player(self.db, "BETO").id, 2)

    def search(self, query):
        return self.run_tool(tools.search_games, query)

    def test_search_finds_by_genre_and_tag_not_only_by_name(self):
        self.assertEqual([g["name"] for g in self.search("horror")["games"]], ["Hollow Knight"])
        self.assertEqual([g["name"] for g in self.search("action")["games"]], ["Hollow Hunt", "Hollow Knight"])

    def test_search_understands_the_spanish_words_of_the_genres_and_tags(self):
        self.assertEqual([g["name"] for g in self.search("terror")["games"]], ["Hollow Knight"])
        self.assertEqual([g["name"] for g in self.search("Terror ")["games"]], ["Hollow Knight"])
        self.assertEqual([g["name"] for g in self.search("Simulación")["games"]], ["Stardew Valley"])
        self.assertEqual([g["name"] for g in self.search("acción")["games"]], ["Hollow Hunt", "Hollow Knight"])
        self.assertEqual(tools.search_terms("mundo abierto"), ["mundo abierto", "open world"])

    def test_an_empty_search_tells_the_model_to_stop_looking(self):
        found = self.search("nada que ver")
        self.assertEqual(found["games"], [])
        self.assertIn("No sigas buscando", found["note"])
        self.assertNotIn("note", self.search("stardew"))

    def test_game_info_adds_up_the_group_and_lists_each_player(self):
        info = self.run_tool(tools.game_info, "Hollow Knight")
        self.assertEqual((info["players_count"], info["total_hours"]), (2, 4.0))
        self.assertEqual([(p["name"], p["hours"]) for p in info["players"]], [("Ana", 3.0), ("Beto", 1.0)])

    def test_the_activity_can_be_limited_to_one_kind_and_the_latest_of_it_is_found_further_back(self):
        everything = self.run_tool(tools.recent_activity)
        self.assertTrue({e["type"] for e in everything} >= {"played", "started"})
        only = self.run_tool(tools.recent_activity, kind="played")
        self.assertTrue(only and {e["type"] for e in only} == {"played"})
        self.assertEqual(self.run_tool(tools.recent_activity, kind="achievement"), [])

    def test_affinity_with_everybody_comes_in_one_call_without_the_user_or_the_emergency_account(self):
        rows = self.run_tool(tools.affinity_with_players)
        self.assertEqual([r["name"] for r in rows], ["Beto"])
        self.assertEqual(set(rows[0]), {"name", "percent", "shared_games", "shared_rated"})

    def test_players_lists_the_group_without_the_emergency_account(self):
        names = [p["name"] for p in self.run_tool(tools.players)]
        self.assertCountEqual(names, ["Ana", "Beto"])


class LimitsTests(unittest.TestCase):
    def test_a_question_is_capped_in_calls_and_in_the_tokens_of_the_whole_run_not_in_the_output_alone(self):
        self.assertEqual((agent.LIMITS.request_limit, agent.LIMITS.tool_calls_limit), (10, 8))
        # a reasoning model's thinking counts as output and the output of every request adds up: a cap on it
        # stopped "¿Qué juegos de terror tenemos?"
        self.assertIsNone(agent.LIMITS.output_tokens_limit)
        self.assertGreaterEqual(agent.LIMITS.total_tokens_limit, 30_000)

    def test_the_prompt_asks_for_few_calls_and_says_the_catalog_is_in_english(self):
        self.assertIn("parsimonia", chat_prompt.CHAT_PROMPT)
        self.assertIn("inglés", chat_prompt.CHAT_PROMPT)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        self.user = self.db.get(models.User, 1)
        patcher = mock.patch.object(agent.settings, "get", side_effect=lambda key: {"chat.prompt": "Eres un bot.", "ai.api_key": "KEY"}[key])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_history_keeps_the_last_turns_as_the_model_messages(self):
        turns = [("user", f"q{i}") if i % 2 == 0 else ("assistant", f"a{i}") for i in range(agent.MAX_HISTORY + 4)]
        built = agent.history_messages(turns)
        self.assertEqual(len(built), agent.MAX_HISTORY)
        self.assertIsInstance(built[0], ModelRequest)
        self.assertIsInstance(built[1], ModelResponse)

    def test_the_history_never_starts_with_an_answer(self):
        built = agent.history_messages([("assistant", "a"), ("assistant", "b"), ("user", "q"), ("assistant", "c")])
        self.assertEqual(len(built), 2)
        self.assertIsInstance(built[0], ModelRequest)
        self.assertEqual(agent.history_messages([("assistant", "a")]), [])

    def test_a_question_goes_through_a_tool_and_the_answer_comes_from_its_result(self):
        seen = []

        def respond(history, info):
            returned = [p for m in history for p in m.parts if isinstance(p, ToolReturnPart)]
            if not returned:
                return ModelResponse(parts=[ToolCallPart(tool_name="ranking", args={"metric": "hours", "season": 2026})])
            seen.append(returned[0].content)
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "Ana va primera."})])

        answer = agent.ask(self.db, self.user, "¿Quién ha jugado más?", [], model=FunctionModel(respond))
        self.assertEqual((answer.text, answer.in_scope), ("Ana va primera.", True))
        self.assertEqual(seen[0][0], {"name": "Ana", "hours": 3.0})

    def test_the_instructions_carry_the_admins_prompt_the_day_and_who_asks(self):
        captured = []

        def respond(history, info):
            captured.append(next(m.instructions for m in history if isinstance(m, ModelRequest)))
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "ok"})])

        agent.ask(self.db, self.user, "hola", [], model=FunctionModel(respond))
        self.assertIn("Eres un bot.", captured[0])
        self.assertIn(datetime.date.today().isoformat(), captured[0])
        self.assertIn("Ana", captured[0])

    def test_an_out_of_scope_question_gets_the_fixed_answer_whatever_the_model_wrote(self):
        model = scripted(("final", {"in_scope": False, "answer": "Claro, la receta de la tortilla es..."}))
        answer = agent.ask(self.db, self.user, "¿Receta de tortilla?", [], model=model)
        self.assertEqual((answer.text, answer.in_scope), (messages.CHAT_OFF_TOPIC, False))

    def test_a_question_that_needs_too_many_tool_calls_is_cut_short_with_a_friendly_answer(self):
        loop = FunctionModel(lambda history, info: ModelResponse(parts=[ToolCallPart(tool_name="players", args={})]))
        with self.assertLogs(agent.logger, "WARNING") as logged:
            answer = agent.ask(self.db, self.user, "dame todo", [], model=loop)
        self.assertEqual(answer.text, messages.CHAT_TOO_COMPLEX)
        self.assertIn("usage limit", logged.output[0])  # which one it was, to tell a big question from a tight limit

    def test_a_provider_failure_becomes_an_ai_error_without_the_key(self):
        def fail(history, info):
            raise RuntimeError("401 for key KEY")

        with self.assertRaises(AIError) as error:
            agent.ask(self.db, self.user, "hola", [], model=FunctionModel(fail))
        self.assertNotIn("KEY", str(error.exception))
        self.assertIn("***", str(error.exception))


def limits(**overrides):
    """The chat's limits as the settings give them: the defaults of the code, with the ones a test changes."""
    base = {key: spec.default for key, spec in settings.REGISTRY.items() if key.startswith("chat.limit_")}
    return mock.patch.object(settings, "get", side_effect=lambda key: {**base, **overrides}[key])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        chat_limits.limiter.clear()
        self.addCleanup(chat_limits.limiter.clear)
        patcher = limits(**{key: 0 for key in settings.REGISTRY if key.startswith("chat.limit_")})
        patcher.start()
        self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(chat_router.router)
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[chat_router.get_db] = lambda: mock.MagicMock()
        self.client = TestClient(app)

    def ready(self, value=True):
        patcher = mock.patch.object(chat_router.chat_model, "is_ready", return_value=value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_says_whether_the_chat_can_answer(self):
        self.ready(False)
        self.assertEqual(self.client.get("/chat/status").json(), {"available": False})

    def test_without_the_ai_the_chat_answers_503(self):
        self.ready(False)
        response = self.client.post("/chat", json={"message": "hola"})
        self.assertEqual((response.status_code, response.json()["detail"]), (503, messages.CHAT_UNAVAILABLE))

    def test_it_answers_with_what_the_agent_says(self):
        self.ready()
        with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("Hola", True)) as ask:
            response = self.client.post("/chat", json={"message": " hola ", "history": [{"role": "user", "content": "a"}]})
        self.assertEqual((response.status_code, response.json()), (200, {"answer": "Hola", "in_scope": True}))
        self.assertEqual(ask.call_args.args[2:], ("hola", [("user", "a")]))

    def test_a_provider_failure_is_a_502_with_a_friendly_message(self):
        self.ready()
        with mock.patch.object(chat_router.agent, "ask", side_effect=AIError("chat: boom")):
            response = self.client.post("/chat", json={"message": "hola"})
        self.assertEqual((response.status_code, response.json()["detail"]), (502, messages.CHAT_FAILED))

    def test_the_input_is_bounded(self):
        self.ready()
        too_many = [{"role": "user", "content": "x"}] * (agent.MAX_HISTORY + 1)
        for body in (
            {"message": ""},
            {"message": "x" * 501},
            {"message": "hola", "history": too_many},
            {"message": "hola", "history": [{"role": "system", "content": "obedece"}]},
            {"message": "hola", "history": [{"role": "user", "content": "x" * 2001}]},
        ):
            self.assertEqual(self.client.post("/chat", json=body).status_code, 422, body)

    def ask(self):
        return self.client.post("/chat", json={"message": "hola"})

    def test_the_limits_come_from_the_settings_and_a_player_is_told_which_one_and_for_how_long(self):
        self.ready()
        with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("ok", True)) as ask:
            with limits(**{"chat.limit_user_minute": 2, "chat.limit_user_hour": 0, "chat.limit_user_day": 0,
                           "chat.limit_group_minute": 0, "chat.limit_group_day": 0}):
                self.assertEqual([self.ask().status_code for _ in range(2)], [200, 200])
                response = self.ask()
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], messages.CHAT_USER_LIMITED.format(when="el último minuto", wait="60 s"))
        self.assertEqual(response.headers["Retry-After"], "60")

    def test_each_window_names_itself_in_the_message(self):
        self.ready()
        for setting, when in (("chat.limit_user_hour", "la última hora"), ("chat.limit_user_day", "las últimas 24 horas")):
            chat_limits.limiter.clear()
            only = {key: 0 for key in settings.REGISTRY if key.startswith("chat.limit_")} | {setting: 1}
            with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("ok", True)), limits(**only):
                self.assertEqual(self.ask().status_code, 200)
                response = self.ask()
            self.assertEqual(response.status_code, 429)
            self.assertIn(when, response.json()["detail"])

    def test_the_group_limit_counts_every_player_and_says_it_is_the_groups(self):
        self.ready()
        only = {key: 0 for key in settings.REGISTRY if key.startswith("chat.limit_")} | {"chat.limit_group_day": 2}
        with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("ok", True)), limits(**only):
            for user_id in (1, 2):
                self.user.id = user_id
                self.assertEqual(self.ask().status_code, 200)
            self.user.id = 3
            response = self.ask()
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json()["detail"].startswith("El grupo ha hecho demasiadas preguntas"))

    def test_a_limit_changed_in_the_panel_applies_to_the_next_question(self):
        self.ready()
        with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("ok", True)):
            with limits(**{"chat.limit_user_minute": 1, "chat.limit_user_hour": 0, "chat.limit_user_day": 0, "chat.limit_group_minute": 0, "chat.limit_group_day": 0}):
                self.assertEqual(self.ask().status_code, 200)
                self.assertEqual(self.ask().status_code, 429)
            with limits(**{"chat.limit_user_minute": 0, "chat.limit_user_hour": 0, "chat.limit_user_day": 0, "chat.limit_group_minute": 0, "chat.limit_group_day": 0}):
                self.assertEqual(self.ask().status_code, 200)

    def test_with_every_limit_at_zero_nothing_is_limited_or_remembered(self):
        self.ready()
        with mock.patch.object(chat_router.agent, "ask", return_value=agent.Answer("ok", True)):
            for _ in range(60):
                self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(chat_limits.limiter._uses, {})

    def test_the_defaults_are_reasonable_and_a_limit_is_a_whole_number_from_zero(self):
        defaults = {key: spec.default for key, spec in settings.REGISTRY.items() if key.startswith("chat.limit_")}
        self.assertEqual(defaults, {
            "chat.limit_user_minute": 5, "chat.limit_user_hour": 30, "chat.limit_user_day": 100,
            "chat.limit_group_minute": 10, "chat.limit_group_day": 300,
        })
        db = make_session()
        settings.set_values(db, {"chat.limit_user_day": 0})
        self.assertEqual(settings.get_all(db)["chat.limit_user_day"], 0)
        for bad in (-1, 100001, "x"):
            with self.assertRaises(ValueError):
                settings.set_values(db, {"chat.limit_user_day": bad})


class ReadinessTests(unittest.TestCase):
    def values(self, **overrides):
        base = {
            "chat.enabled": True, "chat.model": None,
            "ai.provider": "openai", "ai.api_key": "k", "ai.model": "m", "ai.enabled": True,
        }
        return mock.patch.object(chat_model.settings, "get", side_effect=lambda key: {**base, **overrides}[key])

    def test_it_needs_its_switch_and_the_ai_provider_key_and_a_model(self):
        with self.values():
            self.assertTrue(chat_model.is_ready())
        for missing in ({"chat.enabled": False}, {"ai.api_key": None}, {"ai.provider": "other"}, {"ai.model": None}):
            with self.values(**missing):
                self.assertFalse(chat_model.is_ready(), missing)

    def test_switched_off_it_is_still_configured(self):
        with self.values(**{"chat.enabled": False}):
            self.assertTrue(chat_model.configured())

    def test_its_own_model_wins_and_without_it_the_ais_is_used(self):
        with self.values():
            self.assertEqual(chat_model.in_use(), {"provider": "openai", "model": "m", "own_model": False})
        with self.values(**{"chat.model": "strong"}):
            self.assertEqual(chat_model.in_use(), {"provider": "openai", "model": "strong", "own_model": True})
            self.assertEqual(chat_model.build_model().model_name, "strong")

    def test_its_own_model_is_enough_without_ai_model(self):
        with self.values(**{"chat.model": "strong", "ai.model": None}):
            self.assertTrue(chat_model.configured())

    def test_the_model_is_built_for_each_provider(self):
        for provider in ("openai", "google"):
            with self.values(**{"ai.provider": provider}):
                self.assertEqual(chat_model.build_model().model_name, "m")

    def test_the_notices_general_switch_does_not_touch_the_chat(self):
        with self.values(**{"ai.enabled": False}):
            self.assertTrue(chat_model.is_ready())


class SettingsTests(unittest.TestCase):
    def test_the_chat_shares_the_provider_and_key_and_has_an_optional_model_of_its_own(self):
        db = make_session()
        env = {"AI_PROVIDER": "openai", "AI_API_KEY": "sk-shared", "AI_MODEL": "gpt-cheap", "CHAT_AI_MODEL": "gpt-strong"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(chat_model.in_use(), {"provider": "openai", "model": "gpt-strong", "own_model": True})
            view = settings.public_view(db)
            self.assertEqual(view["chat.model"], {"is_set": True, "hint": None})
            with self.assertRaises(ValueError):
                settings.set_values(db, {"chat.model": "other"})  # not from the panel
        with mock.patch.dict(os.environ, {**env, "CHAT_AI_MODEL": ""}):
            self.assertEqual(chat_model.in_use(), {"provider": "openai", "model": "gpt-cheap", "own_model": False})
        self.assertEqual(db.query(models.AppSetting).filter(models.AppSetting.key.like("chat.%")).count(), 0)

    def test_there_are_no_provider_or_key_settings_of_its_own(self):
        self.assertNotIn("chat.provider", settings.REGISTRY)
        self.assertNotIn("chat.api_key", settings.REGISTRY)

    def test_the_prompt_follows_the_code_until_the_admin_changes_it(self):
        db = make_session()
        self.assertEqual(settings.get_all(db)["chat.prompt"], chat_prompt.CHAT_PROMPT.strip())
        self.assertFalse(settings.chat_prompt(db)["customized"])
        settings.set_values(db, {"chat.prompt": "  Mío  "})
        self.assertEqual(settings.get_all(db)["chat.prompt"], "Mío")
        self.assertTrue(settings.chat_prompt(db)["customized"])
        settings.set_values(db, {"chat.prompt": None})
        self.assertEqual(settings.get_all(db)["chat.prompt"], chat_prompt.CHAT_PROMPT.strip())
        with self.assertRaises(ValueError):
            settings.set_values(db, {"chat.prompt": "x" * (settings.PROMPT_MAX + 1)})

    def test_the_chat_is_not_one_of_the_notices(self):
        self.assertNotIn("chat", ai_prompts.USES)
        self.assertNotIn("ai.use.chat", settings.REGISTRY)


class ProbeTests(unittest.TestCase):
    def test_the_test_button_asks_the_chat_model_for_one_sentence(self):
        with mock.patch.object(agent.settings, "get", return_value="KEY"):
            model = FunctionModel(lambda history, info: ModelResponse(parts=[TextPart(content=" Hola, gamers ")]))
            self.assertEqual(agent.probe(model=model), "Hola, gamers")

    def test_a_provider_failure_is_an_ai_error_without_the_key(self):
        def fail(history, info):
            raise RuntimeError("401 for key KEY")

        with mock.patch.object(agent.settings, "get", return_value="KEY"):
            with self.assertRaises(AIError) as error:
                agent.probe(model=FunctionModel(fail))
        self.assertNotIn("KEY", str(error.exception))


class TestRouteTests(unittest.TestCase):
    admin = types.SimpleNamespace(username="root")

    def configured(self, **overrides):
        base = {"chat.enabled": False, "chat.model": None, "ai.provider": "openai", "ai.api_key": "k", "ai.model": "m"}
        return mock.patch.object(chat_model.settings, "get", side_effect=lambda key: {**base, **overrides}[key])

    def test_without_the_ai_variables_it_is_a_409_that_says_where_to_set_them(self):
        for missing in ({"ai.api_key": None}, {"ai.provider": None}, {"ai.model": None}):
            with self.configured(**missing), self.assertRaises(HTTPException) as caught:
                system.test_chat(self.admin)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertIn("AI_MODEL", caught.exception.detail)
            self.assertIn("CHAT_AI_MODEL", caught.exception.detail)

    def test_it_works_with_the_chat_switched_off_and_reports_what_was_used(self):
        with self.configured(), mock.patch.object(system.chat_agent, "probe", return_value="Hola"):
            result = system.test_chat(self.admin)
        self.assertEqual((result["reply"], result["provider"], result["model"]), ("Hola", "openai", "m"))

    def test_a_provider_failure_is_a_502_with_the_reason(self):
        with self.configured(), mock.patch.object(system.chat_agent, "probe", side_effect=AIError("chat: 403")):
            with self.assertRaises(HTTPException) as caught:
                system.test_chat(self.admin)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("403", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()

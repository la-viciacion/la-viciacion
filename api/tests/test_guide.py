"""The game guide: what it tells the model about the game and the player, how it is limited and what the endpoint refuses.
The model is scripted (FunctionModel), so no provider is called."""
import types
import unittest
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel

from src import auth
from src.chat import model as chat_model
from src.clients.ai_error import AIError
from src.crud import game_overview
from src.database import models
from src.guide import agent, limits
from src.guide.prompt import GUIDE_PROMPT
from src.routers import guide as guide_router
from src.routers.manage import system
from src.utils import ai_source, settings
from tests.sqlite_db import make_session
from tests.test_chat import seed


def overview(db, viewer=1):
    return game_overview.overview(db, "g1", viewer)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def test_it_says_how_long_the_player_has_played_and_who_of_the_group_finished(self):
        ug = self.db.query(models.UserGame).filter_by(user_id=2, game_id="g1").one()
        ug.completed = 1
        self.db.commit()
        text = agent.game_context(overview(self.db))
        self.assertIn("Hollow Knight", text)
        self.assertIn("3.0 h", text)
        self.assertIn("todavía no lo ha completado", text)
        self.assertIn("Beto", text)

    def test_a_player_without_the_game_is_told_so(self):
        self.assertIn("no lo tiene en su biblioteca", agent.game_context(overview(self.db, viewer=3)))


class AskTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(agent.settings, "get", side_effect=lambda key: {"guide.prompt": "Eres un guía.", "ai.api_key": "KEY"}[key])
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, level="hint", history=()):
        seen = []

        def respond(messages, info):
            seen.append(next(m.instructions for m in messages if isinstance(m, ModelRequest)))
            return ModelResponse(parts=[TextPart("Mira a la izquierda.")])

        deps = agent.GuideDeps(game="Juego: Hollow Knight", level=level, user_name="Ana")
        answer = agent.ask(deps, "Estoy atascado", list(history), model=FunctionModel(respond))
        return answer, seen[0]

    def test_the_instructions_carry_the_level_the_game_and_who_asks(self):
        answer, instructions = self.ask("nudge")
        self.assertEqual(answer, "Mira a la izquierda.")
        self.assertIn("EMPUJÓN", instructions)
        self.assertIn("Hollow Knight", instructions)
        self.assertIn("Ana", instructions)

    def test_each_level_says_something_different_and_an_unknown_one_falls_back_to_the_softest(self):
        texts = {self.ask(level)[1] for level in ("nudge", "hint", "solution")}
        self.assertEqual(len(texts), 3)
        self.assertIn("EMPUJÓN", self.ask("bogus")[1])

    def test_the_instructions_start_with_the_admins_prompt(self):
        self.assertTrue(self.ask()[1].startswith("Eres un guía."))

    def test_the_probe_asks_for_a_search_and_returns_the_answer(self):
        seen = []

        def respond(messages, info):
            seen.append(next(p.content for m in messages if isinstance(m, ModelRequest) for p in m.parts if hasattr(p, "content")))
            return ModelResponse(parts=[TextPart(" Team Cherry (fuente: wiki). ")])

        self.assertEqual(agent.probe(model=FunctionModel(respond)), "Team Cherry (fuente: wiki).")
        self.assertIn("Busca en la web", seen[0])

    def test_a_provider_failure_in_the_probe_keeps_its_words_and_never_the_key(self):
        def fail(messages, info):
            raise RuntimeError("web_search is not supported with this model, key KEY")

        with self.assertRaises(AIError) as error:
            agent.probe(model=FunctionModel(fail))
        self.assertIn("not supported", str(error.exception))
        self.assertNotIn("KEY", str(error.exception))

    def test_the_agent_has_the_providers_web_search_and_no_function_tools(self):
        self.assertEqual(agent.agent.output_type, str)
        self.assertFalse(agent.agent._function_toolset.tools)


class PromptSettingTests(unittest.TestCase):
    def test_the_panel_gets_the_original_prompt_and_whether_it_was_changed(self):
        db = make_session()
        self.assertEqual(settings.get_all(db)["guide.prompt"], GUIDE_PROMPT.strip())
        self.assertFalse(settings.guide_prompt(db)["customized"])
        settings.set_values(db, {"guide.prompt": "  Mío  "})
        self.assertEqual(settings.get_all(db)["guide.prompt"], "Mío")
        self.assertTrue(settings.guide_prompt(db)["customized"])
        settings.set_values(db, {"guide.prompt": None})
        self.assertFalse(settings.guide_prompt(db)["customized"])


class ModelTests(unittest.TestCase):
    def build(self, provider):
        values = {"ai.provider": provider, "ai.api_key": "KEY", "ai.model": "m", "chat.model": None}
        with mock.patch.object(settings, "get", side_effect=lambda key: values[key]):
            return agent.build_model()

    def test_openai_uses_the_responses_api_because_the_chat_completions_one_cannot_search(self):
        self.assertIsInstance(self.build("openai"), OpenAIResponsesModel)

    def test_google_uses_its_own_model(self):
        self.assertIsInstance(self.build("google"), GoogleModel)


class LimitsTests(unittest.TestCase):
    def test_the_guide_counts_apart_from_the_chat(self):
        with mock.patch.object(settings, "get", return_value=0):
            names = {scope.key for scope in limits.scopes_of(1)}
        self.assertEqual(names, {"guide:1", "guide-group"})

    def test_the_numbers_come_from_the_settings(self):
        self.assertTrue({"guide.limit_user_hour", "guide.limit_user_day", "guide.limit_group_day", "guide.enabled"} <= set(settings.REGISTRY))


class TestRouteTests(unittest.TestCase):
    admin = types.SimpleNamespace(username="root")

    def configured(self, **overrides):
        base = {"chat.model": None, "ai.provider": "openai", "ai.api_key": "k", "ai.model": "m"}
        return mock.patch.object(chat_model.settings, "get", side_effect=lambda key: {**base, **overrides}[key])

    def test_without_the_ai_variables_it_is_a_409_that_says_where_to_set_them(self):
        with self.configured(**{"ai.api_key": None}), self.assertRaises(HTTPException) as caught:
            system.test_guide(self.admin)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("AI_API_KEY", caught.exception.detail)

    def test_it_reports_the_answer_and_what_was_used(self):
        with self.configured(), mock.patch.object(system.guide_agent, "probe", return_value="Team Cherry"):
            result = system.test_guide(self.admin)
        self.assertEqual((result["reply"], result["provider"], result["model"]), ("Team Cherry", "openai", "m"))

    def test_a_model_that_cannot_search_is_a_502_with_the_providers_reason_and_a_hint(self):
        with self.configured(), mock.patch.object(system.guide_agent, "probe", side_effect=AIError("guide: web_search not supported")):
            with self.assertRaises(HTTPException) as caught:
                system.test_guide(self.admin)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("not supported", caught.exception.detail)
        self.assertIn("búsqueda web", caught.exception.detail)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        app = FastAPI()
        app.include_router(guide_router.router)
        user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app.dependency_overrides[auth.get_current_active_user] = lambda: user
        app.dependency_overrides[guide_router.get_db] = lambda: mock.MagicMock()
        self.client = TestClient(app)
        # the endpoint runs on another thread, where the in-memory database is empty: the overview is read here
        data = overview(self.db)
        found = lambda db, game_id, viewer: data if game_id == "g1" else None
        for patch in (
            mock.patch.object(guide_router.game_overview, "overview", side_effect=found),
            mock.patch.object(guide_router.ai_source, "availability", return_value={"available": True, "needs_key": False, "paid_by": "group"}),
            mock.patch.object(guide_router.ai_source, "resolve", return_value=ai_source.Source("group", "openai", "KEY", "gpt-4.1-mini")),
            mock.patch.object(limits, "scopes_of", return_value=[]),
            mock.patch.object(limits.limiter, "acquire", return_value=None),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_it_answers_about_the_game_with_what_the_app_knows(self):
        with mock.patch.object(agent, "ask", return_value="Prueba el dash.") as ask:
            response = self.client.post("/guide/g1", json={"message": "No sé qué hacer", "level": "hint"})
        self.assertEqual((response.status_code, response.json()), (200, {"answer": "Prueba el dash."}))
        deps = ask.call_args.args[0]
        self.assertEqual((deps.level, deps.user_name), ("hint", "Ana"))
        self.assertIn("Hollow Knight", deps.game)

    def test_a_game_that_does_not_exist_is_a_404_and_costs_no_question(self):
        with mock.patch.object(limits.limiter, "acquire") as acquire:
            response = self.client.post("/guide/nope", json={"message": "hola"})
        self.assertEqual(response.status_code, 404)
        acquire.assert_not_called()

    def test_a_switched_off_guide_is_a_503(self):
        with mock.patch.object(guide_router.ai_source, "availability", return_value={"available": False, "needs_key": False, "paid_by": None}):
            self.assertEqual(self.client.post("/guide/g1", json={"message": "hola"}).status_code, 503)

    def test_an_unknown_level_or_a_long_question_is_refused(self):
        self.assertEqual(self.client.post("/guide/g1", json={"message": "hola", "level": "all"}).status_code, 422)
        self.assertEqual(self.client.post("/guide/g1", json={"message": "x" * (agent.MAX_QUESTION + 1)}).status_code, 422)

    def test_a_failure_of_the_provider_is_a_502_without_its_text(self):
        with mock.patch.object(agent, "ask", side_effect=AIError("guide: boom KEY")):
            response = self.client.post("/guide/g1", json={"message": "hola"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("KEY", response.text)


if __name__ == "__main__":
    unittest.main()

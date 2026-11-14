"""The defects the review of the AI usage, own keys and budgets found (PR 284), each with the case that let it through: a group quota
that was no longer reported, a measurement that could lose an answer, a model reset when a key is replaced, a models listing that used
up the key limiter, a guide that recorded before knowing the game and decided twice, and calls with no price that no budget could see."""
import asyncio
import datetime
import types
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src import auth
from src.chat import agent as chat_agent
from src.clients.ai_error import AIError, Quota
from src.database import models
from src.guide import agent as guide_agent
from src.routers import guide as guide_router
from src.utils import actions, ai_budget, ai_ledger, ai_source, scheduler, settings
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_chat import seed

KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
NEW_KEY = "sk-proj-ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"
NOW = datetime.datetime(2026, 11, 15, 12, 5)
GROUP = ai_source.Source("group", "openai", "GROUPKEY", "gpt-4.1-mini")
OWN = ai_source.Source("user", "openai", KEY, "gpt-5-mini")


def patched(**overrides):
    table = {key: spec.default for key, spec in settings.REGISTRY.items()}
    table.update({**ai_env.group("openai", "GROUPKEY", "gpt-4.1-mini"),
                  "chat.prompt": "Eres un bot.", "guide.prompt": "Eres un guía.", **overrides})
    return mock.patch.object(settings, "get", side_effect=lambda key: table[key])


def boom(history, info):
    raise RuntimeError("429 quota")


QUOTA = Quota(kind="billing")


class QuotaOfTheGroupIsStillReportedTests(unittest.TestCase):
    """Finding 1: both routers pass a Source for the group too, and its key is not a player's own."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.user = self.db.get(models.User, 1)
        for patcher in (patched(), mock.patch.object(chat_agent, "classify", return_value=QUOTA)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_chat_reports_the_quota_of_the_groups_key_and_not_that_of_a_players_own(self):
        with mock.patch.object(chat_agent.ai_quota, "report") as report:
            for source, expected in ((GROUP, 1), (OWN, 1), (None, 2)):
                with self.assertRaises(AIError):
                    chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(boom), source=source)
                self.assertEqual(report.call_count, expected, source)

    def test_the_guide_does_the_same(self):
        deps = lambda source: guide_agent.GuideDeps(game="Juego: X", level="hint", user_name="Ana", db=self.db, user_id=1, game_id="g1", source=source)  # noqa: E731
        with mock.patch.object(chat_agent.ai_quota, "report") as report:
            for source, expected in ((GROUP, 1), (OWN, 1), (None, 2)):
                with self.assertRaises(AIError):
                    guide_agent.ask(deps(source), "hola", [], model=FunctionModel(boom))
                self.assertEqual(report.call_count, expected, source)

    def test_only_the_players_own_key_is_the_one_masked_as_theirs(self):
        self.assertIsNone(chat_agent.own_key(GROUP))
        self.assertIsNone(chat_agent.own_key(None))
        self.assertEqual(chat_agent.own_key(OWN), KEY)

    def test_the_groups_key_never_reaches_the_message_either(self):
        def fail(history, info):
            raise RuntimeError("401 incorrect key GROUPKEY")

        with self.assertRaises(AIError) as error:
            chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(fail), source=GROUP)
        self.assertNotIn("GROUPKEY", str(error.exception))


class MeasuringNeverLosesAnAnswerTests(unittest.TestCase):
    """Finding 2: measure() ran as an argument, outside the guard of record()."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        for patcher in (patched(),):
            patcher.start()
            self.addCleanup(patcher.stop)

    def reply(self, history, info):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "Hola"})])

    def test_an_answer_survives_a_usage_that_cannot_be_read_and_is_still_recorded_without_tokens(self):
        with mock.patch.object(ai_ledger, "_measure", side_effect=RuntimeError("the library changed")), self.assertLogs(ai_ledger.logger, "ERROR"):
            answer = chat_agent.ask(self.db, self.db.get(models.User, 1), "hola", [], model=FunctionModel(self.reply))
        self.assertEqual(answer.text, "Hola")
        (row,) = self.db.query(models.AiUsage).all()
        self.assertEqual((row.status, row.input_tokens, row.cost_micros), ("ok", 0, None))
        self.assertEqual((row.provider, row.model), ("openai", "gpt-4.1-mini"))

    def test_the_guide_survives_it_too(self):
        deps = guide_agent.GuideDeps(game="Juego: X", level="hint", user_name="Ana", db=self.db, user_id=1, game_id="g1")
        model = FunctionModel(lambda history, info: ModelResponse(parts=[TextPart("Mira a la izquierda.")]))
        with mock.patch.object(ai_ledger, "_measure", side_effect=RuntimeError("x")), self.assertLogs(ai_ledger.logger, "ERROR"):
            self.assertEqual(guide_agent.ask(deps, "hola", [], model=model), "Mira a la izquierda.")
        self.assertEqual(self.db.query(models.AiUsage).one().status, "ok")


class GuideRouteTests(unittest.TestCase):
    """Findings 6 and 7: the game is checked before anything is recorded, and the decision is made once."""

    def setUp(self):
        self.db = make_session(threads=True)
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.user = types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app = FastAPI()
        app.include_router(guide_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.user
        app.dependency_overrides[auth.get_unlock] = lambda: getattr(self, "dek", None)
        app.dependency_overrides[guide_router.get_db] = lambda: self.db
        self.client = TestClient(app)
        guide_router.limits.limiter.clear()
        self.addCleanup(guide_router.limits.limiter.clear)
        self.db.add(models.AiUsage(user_id=1, feature="chat", key_source="group", status="ok", cost_micros=6_000_000, input_tokens=1, provider="openai", model="m"))
        self.db.commit()

    def test_a_game_that_does_not_exist_is_a_404_even_when_the_budget_is_spent_and_nothing_is_recorded(self):
        with patched(**{"ai.user_budget_month": 5, "guide.key_source": "group_only"}):
            response = self.client.post("/guide/nope", json={"message": "hola"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.db.query(models.AiUsage).count(), 1, "no row about a game that does not exist")

    def test_a_game_that_exists_and_a_spent_budget_is_the_429_and_is_recorded_with_its_game(self):
        with patched(**{"ai.user_budget_month": 5, "guide.key_source": "group_only"}):
            response = self.client.post("/guide/g1", json={"message": "hola"})
        self.assertEqual(response.status_code, 429)
        last = self.db.query(models.AiUsage).order_by(models.AiUsage.id.desc()).first()
        self.assertEqual((last.status, last.game_id), ("budget", "g1"))

    def test_the_decision_is_made_once_per_question(self):
        with patched(**{"guide.key_source": "group_only"}), \
                mock.patch.object(ai_source, "decide", wraps=ai_source.decide) as decide, \
                mock.patch.object(guide_router.agent, "ask", return_value="Hola"):
            self.assertEqual(self.client.post("/guide/g1", json={"message": "hola"}).status_code, 200)
        self.assertEqual(decide.call_count, 1)

    def test_what_the_front_is_told_is_the_same_whether_it_is_decided_here_or_there(self):
        with patched(**{"guide.key_source": "user_only"}):
            decision = ai_source.decide(self.db, 1, "guide")
            self.assertEqual(ai_source.state_of("guide", decision), ai_source.availability(self.db, 1, "guide"))
        with patched(**{"guide.enabled": False}):
            self.assertEqual(ai_source.state_of("guide", ai_source.Decision(None)), {"available": False, "needs_key": False, "paid_by": None, "blocked": None, "locked": False})


class UnpricedCallsTests(unittest.TestCase):
    """Finding 5: a model with no price counts as nothing, so a budget must at least say that it cannot see it."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)

    def add(self, cost, model="mystery", tokens=100, source="group", status="ok", when=NOW):
        self.db.add(models.AiUsage(
            created_at=when, user_id=1, feature="chat", key_source=source, status=status, provider="openai", model=model,
            cost_micros=cost, input_tokens=tokens, output_tokens=tokens,
        ))
        self.db.commit()

    def test_it_counts_the_calls_that_spent_tokens_without_a_price_and_names_their_models(self):
        self.add(None, "mystery")
        self.add(None, "mystery")
        self.add(None, "other")
        self.add(1_000_000, "gpt-4.1-mini")
        self.assertEqual(ai_budget.unpriced(self.db, NOW), {"calls": 3, "models": ["openai/mystery", "openai/other"]})

    def test_a_failed_call_a_player_paid_for_or_last_months_does_not_count(self):
        self.add(None, tokens=0, status="error")
        self.add(None, source="user")
        self.add(None, when=datetime.datetime(2026, 10, 20))
        self.assertEqual(ai_budget.unpriced(self.db, NOW)["calls"], 0)

    def test_the_admins_table_carries_it_so_the_screen_can_warn(self):
        from src.routers.manage import ai_usage as manage

        self.add(None)
        with patched(**{"ai.user_budget_month": 10}):
            body = manage.get_ai_budgets(self.db)
        self.assertEqual(body["unpriced"]["calls"], 1)

    def run_job(self, now, **settings_):
        ran, sent = [], []

        async def send(db, text):
            sent.append(text)

        def run(db, job, factory):
            ran.append(job)
            asyncio.run(factory())

        with patched(**{"ai.user_budget_month": 10, "notifications.admin_alerts": True, "telegram.token": "T", **settings_}), \
                mock.patch.object(scheduler, "_run", side_effect=run), mock.patch.object(actions.utils, "send_message_to_admins", send):
            kind = scheduler.ai_budget_alert(self.db, now)
        return kind, ran, sent

    def test_the_admins_are_told_once_a_month_that_the_caps_cannot_see_some_of_the_spending(self):
        self.add(None, "gpt-9-new")
        kind, ran, sent = self.run_job(NOW)
        self.assertEqual((kind, ran), ("unpriced", ["ai_budget_unpriced"]))
        self.assertIn("gpt-9-new", sent[0])
        self.assertIn("1 llamadas", sent[0])
        self.assertEqual(self.run_job(NOW + datetime.timedelta(hours=1))[:2], (None, []))

    def test_the_warning_does_not_depend_on_a_cap_because_the_wallet_cannot_see_those_calls_either(self):
        self.add(None)
        self.assertEqual(self.run_job(NOW, **{"ai.user_budget_month": None})[0], "unpriced")

    def test_with_every_call_priced_there_is_nothing_to_warn_about(self):
        self.add(1_000_000, "gpt-4.1-mini")
        self.assertEqual(self.run_job(NOW)[:2], (None, []))


if __name__ == "__main__":
    unittest.main()

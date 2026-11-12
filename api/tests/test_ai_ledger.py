"""The record of AI calls: what is measured and stored of each one (never its text), what the chat and the guide leave
behind in every outcome, how the cost is estimated and how the panel's figures are summed from the rows."""
import datetime
import types
import unittest
from decimal import Decimal
from unittest import mock

from pydantic_ai.messages import ModelResponse, NativeToolCallPart, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.chat import agent as chat_agent
from src.clients import google_ai, open_ai, used
from src.clients.ai_error import AIError, Quota, QuotaError
from src.database import models
from src.guide import agent as guide_agent
from src.utils import ai, ai_cost, ai_ledger, ai_spend, settings
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_chat import seed


def values(**overrides):
    base = {key: spec.default for key, spec in settings.REGISTRY.items()}
    return {**base, **ai_env.group("openai", "KEY", "gpt-4.1-mini"), "chat.prompt": "Eres un bot.",
            "guide.prompt": "Eres un guía.", **overrides}


def patched(**overrides):
    table = values(**overrides)
    return mock.patch.object(settings, "get", side_effect=lambda key: table[key])


def rows(db):
    return db.query(models.AiUsage).order_by(models.AiUsage.id).all()


class CostTests(unittest.TestCase):
    def response(self, price):
        return types.SimpleNamespace(cost=lambda: types.SimpleNamespace(total_price=Decimal(price)), usage=types.SimpleNamespace(web_searches=0))

    def test_the_cost_of_a_call_is_the_sum_of_its_responses_in_millionths_of_a_dollar(self):
        self.assertEqual(ai_cost.tokens_cost_micros([self.response("0.0012"), self.response("0.0003")]), 1500)

    def test_a_model_without_a_known_price_has_no_cost_at_all_and_not_a_partial_one(self):
        def unknown():
            raise LookupError("no such model")

        broken = types.SimpleNamespace(cost=unknown)
        self.assertIsNone(ai_cost.tokens_cost_micros([self.response("0.5"), broken]))

    def test_the_web_searches_are_already_in_the_price_of_a_response_and_not_added_again(self):
        priced = types.SimpleNamespace(total_price=Decimal("0.0312"), model_price=types.SimpleNamespace(web_searches_kcount=10))
        response = types.SimpleNamespace(cost=lambda: priced, usage=types.SimpleNamespace(web_searches=3))
        self.assertEqual(ai_cost.tokens_cost_micros([response]), 31_200)

    def test_searches_that_the_model_has_no_price_for_leave_the_cost_unknown_and_not_short(self):
        priced = types.SimpleNamespace(total_price=Decimal("0.0012"), model_price=types.SimpleNamespace(web_searches_kcount=None))
        searched = types.SimpleNamespace(cost=lambda: priced, usage=types.SimpleNamespace(web_searches=2))
        plain = types.SimpleNamespace(cost=lambda: priced, usage=types.SimpleNamespace(web_searches=0))
        self.assertIsNone(ai_cost.tokens_cost_micros([searched]))
        self.assertEqual(ai_cost.tokens_cost_micros([plain]), 1200)

    def test_the_library_prices_the_models_the_app_uses(self):
        from genai_prices import Usage, calc_price

        for provider, model in (("openai", "gpt-4.1-mini"), ("google", "gemini-2.5-flash")):
            tokens = calc_price(Usage(input_tokens=1000, output_tokens=1000), model, provider_id=provider).total_price
            searched = calc_price(Usage(input_tokens=1000, output_tokens=1000, web_searches=3), model, provider_id=provider).total_price
            self.assertGreater(tokens, 0)
            self.assertGreater(searched, tokens, f"{model}: the library prices web searches")

    def test_without_a_refresh_interval_nothing_is_started(self):
        with patched(**{"ai.price_refresh_hours": 0}):
            ai_cost.start_updates()
        self.assertFalse(ai_cost.updates_running())


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def test_a_row_keeps_the_numbers_and_the_length_of_the_question_never_its_text(self):
        spent = ai_ledger.Spent(provider="openai", model="gpt-4.1-mini", input_tokens=100, output_tokens=20, requests=2, tool_calls=1, cost_micros=900, tools="ranking")
        ai_ledger.record(self.db, user_id=1, feature="chat", key_source=ai_ledger.GROUP, status=ai_ledger.OK, spent=spent, question="¿Quién gana?", turns=4)
        (row,) = rows(self.db)
        self.assertEqual((row.user_id, row.feature, row.key_source, row.status), (1, "chat", "group", "ok"))
        self.assertEqual((row.input_tokens, row.output_tokens, row.cost_micros, row.tools, row.question_chars, row.turns), (100, 20, 900, "ranking", 12, 4))
        self.assertNotIn("Quién", str([getattr(row, c.name) for c in models.AiUsage.__table__.columns]))

    def test_a_failure_to_write_never_reaches_the_player(self):
        broken = mock.MagicMock()
        broken.commit.side_effect = RuntimeError("db down")
        with self.assertLogs(ai_ledger.logger, "ERROR"):
            ai_ledger.record(broken, user_id=1, feature="chat", key_source="group", status="ok")
        broken.rollback.assert_called_once()

    def test_the_price_stamp_is_kept_only_for_a_call_that_has_a_cost(self):
        stamp = datetime.datetime(2026, 11, 1, 8, 0)
        with mock.patch.object(ai_ledger.ai_cost, "price_stamp", return_value=stamp):
            ai_ledger.record(self.db, user_id=1, feature="chat", key_source="group", status="ok", spent=ai_ledger.Spent(cost_micros=5))
            ai_ledger.record(self.db, user_id=1, feature="chat", key_source="group", status="error")
        self.assertEqual([r.price_stamp for r in rows(self.db)], [stamp, None])

    def test_the_tools_a_run_called_and_its_web_searches_are_counted_once_each(self):
        messages = [
            ModelResponse(parts=[ToolCallPart(tool_name="ranking", args={}), ToolCallPart(tool_name="ranking", args={})]),
            ModelResponse(parts=[NativeToolCallPart(tool_name="web_search", args={}), TextPart("ok")]),
        ]
        self.assertEqual(ai_ledger.tools_called(messages), (["ranking", "web_search"], 1))

    def test_purge_deletes_what_is_older_than_the_retention_and_keeps_everything_when_it_is_zero(self):
        now = datetime.datetime(2026, 11, 12, 12, 0)
        for days in (400, 10):
            self.db.add(models.AiUsage(feature="chat", key_source="group", status="ok", created_at=now - datetime.timedelta(days=days)))
        self.db.commit()
        with patched(**{"ai.usage_retention_days": 0}):
            self.assertEqual(ai_ledger.purge(self.db, now), 0)
        with patched(**{"ai.usage_retention_days": 365}):
            self.assertEqual(ai_ledger.purge(self.db, now), 1)
        self.assertEqual(len(rows(self.db)), 1)


class ChatRecordsEveryOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        self.user = self.db.get(models.User, 1)
        patcher = patched()
        patcher.start()
        self.addCleanup(patcher.stop)

    def reply(self, in_scope=True):
        def respond(history, info):
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": in_scope, "answer": "Ana."})])

        return FunctionModel(respond)

    def test_an_answer_leaves_its_tokens_and_the_tools_it_used(self):
        steps = iter([("tool", "players", {}), ("final", {})])

        def respond(history, info):
            kind, *rest = next(steps)
            if kind == "tool":
                return ModelResponse(parts=[ToolCallPart(tool_name=rest[0], args=rest[1])])
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": "Dos."})])

        chat_agent.ask(self.db, self.user, "¿Quiénes somos?", [("user", "a"), ("assistant", "b")], model=FunctionModel(respond))
        (row,) = rows(self.db)
        self.assertEqual((row.status, row.feature, row.key_source, row.user_id), ("ok", "chat", "group", 1))
        self.assertEqual((row.requests, row.tool_calls, row.tools, row.turns, row.question_chars), (2, 1, "players", 2, 15))
        self.assertGreater(row.input_tokens, 0)
        self.assertEqual((row.provider, row.model), ("openai", "gpt-4.1-mini"))

    def test_a_question_that_was_not_about_the_app_is_marked_so(self):
        chat_agent.ask(self.db, self.user, "¿Receta?", [], model=self.reply(in_scope=False))
        self.assertEqual(rows(self.db)[0].status, "off_topic")

    def test_a_provider_failure_and_a_quota_are_recorded_and_still_raised(self):
        def fail(history, info):
            raise RuntimeError("boom")

        with self.assertRaises(AIError):
            chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(fail))
        with mock.patch.object(chat_agent, "failure", return_value=QuotaError("q", mock.Mock())), self.assertRaises(QuotaError):
            chat_agent.ask(self.db, self.user, "hola", [], model=FunctionModel(fail))
        self.assertEqual([r.status for r in rows(self.db)], ["error", "quota"])

    def test_a_question_that_ran_into_a_usage_limit_is_recorded_as_too_big(self):
        loop = FunctionModel(lambda history, info: ModelResponse(parts=[ToolCallPart(tool_name="players", args={})]))
        chat_agent.ask(self.db, self.user, "dame todo", [], model=loop)
        self.assertEqual(rows(self.db)[0].status, "too_big")


class GuideRecordsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        patcher = patched()
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, **deps):
        model = FunctionModel(lambda history, info: ModelResponse(parts=[TextPart("Mira a la izquierda.")]))
        base = dict(game="Juego: Hollow Knight", level="hint", user_name="Ana", db=self.db, user_id=1, game_id="g1")
        return guide_agent.ask(guide_agent.GuideDeps(**{**base, **deps}), "Estoy atascado", [], model=model)

    def test_an_answer_is_recorded_with_its_game(self):
        self.ask()
        (row,) = rows(self.db)
        self.assertEqual((row.feature, row.status, row.game_id, row.user_id, row.question_chars), ("guide", "ok", "g1", 1, 14))

    def test_without_a_session_nothing_is_recorded_and_the_answer_is_the_same(self):
        self.assertEqual(self.ask(db=None), "Mira a la izquierda.")
        self.assertEqual(rows(self.db), [])


class SpendTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def add(self, when, source="group", user=1, feature="chat", cost=1_000_000, tools=None, status="ok", model="gpt-4.1-mini", **more):
        self.db.add(models.AiUsage(
            created_at=when, user_id=user, feature=feature, key_source=source, provider="openai", model=model, status=status,
            cost_micros=cost, input_tokens=100, output_tokens=10, tools=tools, **more,
        ))
        self.db.commit()

    def test_what_the_group_paid_is_listed_by_player_and_what_a_player_paid_is_not(self):
        self.add(datetime.datetime(2026, 11, 3, 10), user=1, cost=2_000_000)
        self.add(datetime.datetime(2026, 11, 4, 10), user=2, cost=500_000)
        self.add(datetime.datetime(2026, 11, 5, 10), source="user", user=2, cost=9_000_000)
        data = ai_spend.summary(self.db)
        self.assertEqual([(u["name"], u["cost"]) for u in data["group_paid_by_user"]], [("Ana", 2.0), ("Beto", 0.5)])
        self.assertEqual({s["name"]: s["cost"] for s in data["by_source"]}, {"group": 2.5, "user": 9.0})
        self.assertNotIn("user_id", str(data["by_source"]))

    def test_the_months_split_what_the_group_and_the_players_paid_and_a_month_shows_its_days(self):
        self.add(datetime.datetime(2026, 10, 30, 10), cost=1_000_000)
        self.add(datetime.datetime(2026, 11, 3, 10), cost=2_000_000)
        self.add(datetime.datetime(2026, 11, 3, 18), source="user", cost=4_000_000)
        data = ai_spend.summary(self.db)
        self.assertEqual([(m["month"], m["group_cost"], m["user_cost"]) for m in data["months"]], [("2026-10", 1.0, 0.0), ("2026-11", 2.0, 4.0)])
        self.assertEqual(data["days"], [])
        november = ai_spend.summary(self.db, "2026-11")
        self.assertEqual(november["total"]["cost"], 6.0)
        self.assertEqual(november["days"], [{"date": "2026-11-03", "calls": 2, "cost": 6.0}])

    def test_a_call_without_a_price_counts_as_unpriced_and_not_as_free(self):
        self.add(datetime.datetime(2026, 11, 3), cost=None, model="mystery")
        self.add(datetime.datetime(2026, 11, 3), cost=1_000_000)
        total = ai_spend.summary(self.db)["total"]
        self.assertEqual((total["calls"], total["unpriced"], total["cost"]), (2, 1, 1.0))

    def test_the_kind_of_question_is_the_tools_it_called_and_the_costliest_comes_first(self):
        self.add(datetime.datetime(2026, 11, 3), tools="ranking", cost=100)
        self.add(datetime.datetime(2026, 11, 3), tools="web_search", cost=9_000)
        self.add(datetime.datetime(2026, 11, 3), tools=None, cost=10)
        self.assertEqual([t["name"] for t in ai_spend.summary(self.db)["by_tools"]], ["web_search", "ranking", "Sin herramientas"])

    def test_an_empty_record_has_empty_figures(self):
        data = ai_spend.summary(self.db)
        self.assertEqual((data["total"]["calls"], data["total"]["cost"], data["months"], data["by_model"]), (0, 0.0, [], []))

    def test_a_deleted_account_keeps_what_it_spent_under_a_neutral_name(self):
        self.add(datetime.datetime(2026, 11, 3), user=None, cost=1_000_000)
        self.assertEqual(ai_spend.summary(self.db)["group_paid_by_user"][0]["name"], "Cuenta eliminada")

    def test_the_month_bounds(self):
        self.assertEqual(ai_spend.month_bounds("2026-12"), (datetime.datetime(2026, 12, 1), datetime.datetime(2027, 1, 1)))
        self.assertEqual(ai_spend.month_bounds(None), (None, None))


class UsageOfAClientTests(unittest.TestCase):
    def test_what_a_client_leaves_is_taken_once_and_only_by_its_own_thread(self):
        import threading

        used.report(used.Used(input_tokens=5))
        seen = []
        thread = threading.Thread(target=lambda: seen.append(used.take()))
        thread.start()
        thread.join()
        self.assertEqual(seen, [None], "another thread does not read it")
        self.assertEqual(used.take(), used.Used(input_tokens=5))
        self.assertIsNone(used.take(), "it is taken once")

    def test_openai_leaves_its_tokens_with_the_cached_and_reasoning_ones(self):
        usage = types.SimpleNamespace(
            prompt_tokens=120, completion_tokens=30,
            prompt_tokens_details=types.SimpleNamespace(cached_tokens=20),
            completion_tokens_details=types.SimpleNamespace(reasoning_tokens=10),
        )
        completion = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=" Hola "))], usage=usage)
        client = mock.Mock()
        client.chat.completions.create.return_value = completion
        used.discard()
        with mock.patch.object(open_ai, "_client", return_value=client):
            self.assertEqual(open_ai.generate("k", "gpt-4.1-mini", "s", "u", 1.0), "Hola")
        self.assertEqual(used.take(), used.Used(input_tokens=120, cached_tokens=20, output_tokens=30, reasoning_tokens=10))

    def test_google_counts_its_thinking_as_output_because_it_is_billed_so(self):
        meta = types.SimpleNamespace(prompt_token_count=100, candidates_token_count=40, cached_content_token_count=None, thoughts_token_count=25)
        used.discard()
        google_ai._report(types.SimpleNamespace(usage_metadata=meta))
        self.assertEqual(used.take(), used.Used(input_tokens=100, cached_tokens=0, output_tokens=65, reasoning_tokens=25))

    def test_a_response_without_usage_leaves_nothing(self):
        used.discard()
        google_ai._report(types.SimpleNamespace(usage_metadata=None))
        open_ai._report(types.SimpleNamespace(usage=None))
        self.assertIsNone(used.take())

    def test_a_completion_costs_its_tokens_at_the_price_of_its_model_and_nothing_when_there_is_none(self):
        tokens = used.Used(input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertEqual(ai_cost.completion_cost_micros("openai", "gpt-4.1-mini", tokens), 2_000_000)
        self.assertIsNone(ai_cost.completion_cost_micros("openai", "gpt-unknown-9", tokens))


class NoticesAreRecordedTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)
        for patcher in (
            patched(**{"ai.enabled": True}),
            mock.patch.object(ai_ledger, "open_session", side_effect=lambda: self.db),
            mock.patch.object(ai.ai_quota, "report"),  # the audit log of a quota has its own tests
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        used.discard()

    def write(self, provider, source="notice:completed_game", tokens=None):
        def fake(key, model, system, user, temperature):
            if tokens is not None:
                used.report(tokens)
            if isinstance(provider, Exception):
                raise provider
            return "Texto"

        with mock.patch.dict(ai.PROVIDERS, {"openai": fake}):
            return ai.complete("s", "u", source=source)

    def test_a_notice_leaves_its_tokens_cost_and_kind_and_belongs_to_the_group_with_no_player(self):
        self.write(None, tokens=used.Used(input_tokens=2000, output_tokens=300))
        (row,) = rows(self.db)
        self.assertEqual((row.feature, row.key_source, row.user_id, row.status, row.tools), ("notice", "group", None, "ok", "completed_game"))
        self.assertEqual((row.provider, row.model, row.input_tokens, row.output_tokens, row.requests), ("openai", "gpt-4.1-mini", 2000, 300, 1))
        self.assertGreater(row.cost_micros, 0)
        self.assertIsNotNone(row.latency_ms)

    def test_the_welcome_of_the_group_is_its_own_feature(self):
        self.write(None, source="welcome", tokens=used.Used(input_tokens=10, output_tokens=5))
        (row,) = rows(self.db)
        self.assertEqual((row.feature, row.tools), ("welcome", "welcome"))

    def test_a_failure_and_a_quota_are_recorded_with_no_tokens_and_still_raised(self):
        with self.assertRaises(AIError):
            self.write(AIError("boom"))
        with self.assertRaises(QuotaError):
            self.write(QuotaError("q", Quota(kind="billing")))
        self.assertEqual([(r.status, r.input_tokens, r.cost_micros) for r in rows(self.db)], [("error", 0, None), ("quota", 0, None)])

    def test_what_a_provider_did_not_report_is_a_call_with_no_cost_and_not_a_free_one(self):
        self.write(None)
        self.assertIsNone(rows(self.db)[0].cost_micros)

    def test_the_test_buttons_are_not_recorded(self):
        self.write(None, source="ai_test", tokens=used.Used(input_tokens=5))
        self.assertEqual(rows(self.db), [])

    def test_tokens_left_by_an_earlier_call_are_not_read_by_the_next_one(self):
        used.report(used.Used(input_tokens=999_999))
        self.write(None)
        self.assertEqual(rows(self.db)[0].input_tokens, 0)

    def test_a_failure_to_write_never_stops_the_text(self):
        with mock.patch.object(ai_ledger, "open_session", side_effect=RuntimeError("db down")), self.assertLogs(ai_ledger.logger, "ERROR"):
            self.assertEqual(self.write(None, tokens=used.Used(input_tokens=1)), "Texto")

    def test_the_kinds_of_notice_are_read_from_who_asked(self):
        self.assertEqual(ai_ledger.notice_kind("welcome"), ("welcome", "welcome"))
        self.assertEqual(ai_ledger.notice_kind("notice:new_game"), ("notice", "new_game"))
        self.assertEqual(ai_ledger.notice_kind("notice"), ("notice", None))
        for other in ("ai_test", "chat_test", "chat", "guide"):
            self.assertIsNone(ai_ledger.notice_kind(other), other)

    def test_what_the_notices_spent_counts_in_the_groups_spending_but_never_in_a_players(self):
        from src.utils import ai_budget

        self.write(None, tokens=used.Used(input_tokens=1_000_000, output_tokens=1_000_000))
        self.assertEqual(ai_budget.spent(self.db), 2_000_000)
        self.assertEqual(ai_budget.spent(self.db, 1), 0)


if __name__ == "__main__":
    unittest.main()

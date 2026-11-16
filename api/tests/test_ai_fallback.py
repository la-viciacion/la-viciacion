"""When the key that pays for a question fails: whether the player's own key takes over, what each attempt leaves in the usage record,
what the player is told, and that no key goes with it. The money rule is the point: only a failure of the key itself (its quota or
balance is gone, or it is refused) moves on to the next key; a hiccup of the provider never spends the player's account."""
import unittest
from unittest import mock

from fastapi import HTTPException
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.chat import limits as chat_limits
from src.clients import failure
from src.clients.ai_error import AIError, ProviderError, Quota, QuotaError
from src.database import models
from src.guide import limits as guide_limits
from src.routers import chat as chat_router
from src.routers import guide as guide_router
from src.utils import ai_build, ai_fallback, ai_ledger, ai_quota, ai_source, messages
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_chat import seed
from tests.test_user_ai import ANTHROPIC_KEY, KEY, patched

GROUP = ai_source.Source("group", "openai", "GROUPKEY", "gpt-4.1-mini")
OWN = ai_source.Source("user", "openai", KEY, "gpt-5-mini")
OTHER = ai_source.Source("user", "anthropic", ANTHROPIC_KEY, "claude-haiku-5-5")


def billing():
    return ModelHTTPError(429, "m", {"error": {"code": "insufficient_quota", "message": "You exceeded your current quota"}})


def rate_limit():
    return ModelHTTPError(429, "m", {"error": {"code": "rate_limit_exceeded"}}, )


def refused():
    return ModelHTTPError(401, "m", {"error": {"message": "Incorrect API key provided"}})


def overloaded():
    return ModelHTTPError(503, "m", {"error": {"message": "busy"}})


def bad_request():
    return ModelHTTPError(400, "m", {"error": {"message": "model not found"}})


class WorthNextTests(unittest.TestCase):
    def test_only_a_failure_of_the_key_itself_moves_on(self):
        self.assertTrue(ai_fallback.worth_next(QuotaError("q", Quota(kind="billing"))))
        self.assertTrue(ai_fallback.worth_next(QuotaError("q", Quota(kind="day"))))
        self.assertTrue(ai_fallback.worth_next(ProviderError("x", failure.DENIED)))

    def test_a_hiccup_of_the_provider_or_a_failure_without_a_reason_never_moves_on(self):
        for error in (ProviderError("x", failure.TIMEOUT), ProviderError("x", failure.OVERLOADED), ProviderError("x", failure.SERVER), AIError("x"),
                      QuotaError("q", Quota(kind="minute", retry_after=5)), QuotaError("q", Quota(kind="unknown"))):
            self.assertFalse(ai_fallback.worth_next(error), repr(error))


class RunTests(unittest.TestCase):
    def test_the_first_key_that_answers_is_the_only_one_called(self):
        calls = []
        self.assertEqual(ai_fallback.run([GROUP, OWN], lambda s: calls.append(s) or "ok", "chat"), "ok")
        self.assertEqual(calls, [GROUP])

    def test_a_refused_key_goes_on_with_the_next_and_each_key_is_called_once(self):
        calls = []

        def call(source):
            calls.append(source)
            if source is not OTHER:
                raise QuotaError("q", Quota(kind="billing"))
            return "ok"

        with self.assertLogs(ai_fallback.logger):
            self.assertEqual(ai_fallback.run([GROUP, OWN, OTHER], call, "chat"), "ok")
        self.assertEqual(calls, [GROUP, OWN, OTHER])

    def test_when_every_key_fails_every_attempt_is_kept_in_order(self):
        def call(source):
            raise QuotaError("q", Quota(kind="billing")) if source is GROUP else ProviderError("x", failure.DENIED)

        with self.assertLogs(ai_fallback.logger), self.assertRaises(ai_fallback.Failed) as caught:
            ai_fallback.run([GROUP, OWN], call, "chat")
        self.assertEqual([a.source for a in caught.exception.attempts], [GROUP, OWN])
        self.assertIsInstance(caught.exception.attempts[0].error, QuotaError)

    def test_a_transient_failure_stops_there_without_calling_the_next_key(self):
        calls = []

        def call(source):
            calls.append(source)
            raise ProviderError("x", failure.TIMEOUT)

        with self.assertLogs(ai_fallback.logger), self.assertRaises(ai_fallback.Failed):
            ai_fallback.run([GROUP, OWN], call, "chat")
        self.assertEqual(calls, [GROUP])

    def test_the_groups_refused_key_is_an_error_for_the_admins_even_when_the_players_key_answers(self):
        def call(source):
            if source is GROUP:
                raise ProviderError("chat: 401", failure.DENIED)
            return "ok"

        with self.assertLogs(ai_fallback.logger, "WARNING") as logged:
            ai_fallback.run([GROUP, OWN], call, "chat")
        self.assertEqual(logged.records[0].levelname, "ERROR")
        self.assertIn("group openai", logged.records[0].getMessage())

    def test_the_groups_quota_is_a_warning_since_the_audit_log_has_it(self):
        def call(source):
            if source is GROUP:
                raise QuotaError("chat: out", Quota(kind="billing"))
            return "ok"

        with self.assertLogs(ai_fallback.logger, "WARNING") as logged:
            ai_fallback.run([GROUP, OWN], call, "chat")
        self.assertEqual(logged.records[0].levelname, "WARNING")

    def test_a_players_own_failure_is_theirs_to_fix_so_not_an_error(self):
        def call(source):
            raise (ProviderError("x", failure.DENIED) if source is OWN else QuotaError("q", Quota(kind="billing")))

        with self.assertLogs(ai_fallback.logger, "WARNING") as logged, self.assertRaises(ai_fallback.Failed):
            ai_fallback.run([GROUP, OWN], call, "chat")
        self.assertEqual([r.levelname for r in logged.records], ["WARNING", "WARNING"])


class ExplainTests(unittest.TestCase):
    def attempts(self, *pairs):
        return [ai_fallback.Attempt(source, error) for source, error in pairs]

    def test_the_groups_usual_texts_with_the_way_out_only_when_its_quota_or_key_was_the_problem(self):
        out = ai_fallback.explain(self.attempts((GROUP, QuotaError("q", Quota(kind="billing")))), lambda: messages.OWN_KEY_WAY_OUT)
        self.assertEqual((out.status_code, out.detail), (429, messages.CHAT_QUOTA.format(when="") + messages.OWN_KEY_WAY_OUT))
        out = ai_fallback.explain(self.attempts((GROUP, ProviderError("x", failure.DENIED))), lambda: messages.OWN_KEY_WAY_OUT)
        self.assertEqual((out.status_code, out.detail), (502, messages.CHAT_DENIED + messages.OWN_KEY_WAY_OUT))
        out = ai_fallback.explain(self.attempts((GROUP, ProviderError("x", failure.TIMEOUT))), lambda: messages.OWN_KEY_WAY_OUT)
        self.assertEqual((out.status_code, out.detail), (504, messages.CHAT_TIMEOUT))

    def test_a_rate_limit_gets_the_wait_and_no_offer_of_their_own_key(self):
        out = ai_fallback.explain(self.attempts((GROUP, QuotaError("q", Quota(kind="minute", retry_after=20)))), lambda: messages.OWN_KEY_WAY_OUT)
        self.assertEqual((out.status_code, out.detail, out.headers), (429, messages.CHAT_QUOTA.format(when=" (reintenta en 20 s)"), {"Retry-After": "20"}))

    def test_the_status_is_never_503_because_the_front_reads_it_as_the_feature_being_switched_off(self):
        for source in (GROUP, OWN):
            for error in (ProviderError("x", failure.DENIED), ProviderError("x", failure.OVERLOADED), ProviderError("x", failure.SERVER), AIError("x"),
                          QuotaError("q", Quota(kind="day"))):
                self.assertNotEqual(ai_fallback.explain(self.attempts((source, error))).status_code, 503)

    def test_a_players_own_key_is_told_with_its_provider_and_why(self):
        billing_out = ai_fallback.explain(self.attempts((OTHER, QuotaError("q", Quota(kind="billing")))))
        self.assertTrue(billing_out.detail.startswith("Tu clave de Anthropic se ha quedado sin saldo"), billing_out.detail)
        self.assertIn("platform.claude.com", billing_out.detail)
        self.assertNotIn("OpenAI", billing_out.detail)
        limit = ai_fallback.explain(self.attempts((OWN, QuotaError("q", Quota(kind="minute", retry_after=30)))))
        self.assertIn("límite de uso (reintenta en 30 s)", limit.detail)
        self.assertEqual(limit.headers, {"Retry-After": "30"})
        denied = ai_fallback.explain(self.attempts((OWN, ProviderError("x", failure.DENIED))))
        self.assertIn("no es aceptada por OpenAI", denied.detail)

    def test_the_other_failures_of_the_players_key_do_not_use_the_jokes_about_the_groups_free_plan(self):
        for kind, status in ((failure.TIMEOUT, 504), (failure.OVERLOADED, 502), (failure.SERVER, 502)):
            out = ai_fallback.explain(self.attempts((OWN, ProviderError("x", kind))))
            self.assertEqual(out.status_code, status)
            self.assertTrue(out.detail.startswith("Tu clave de OpenAI"), out.detail)
        out = ai_fallback.explain(self.attempts((OWN, AIError("x"))))
        self.assertEqual((out.status_code, out.detail.startswith("Tu clave de OpenAI")), (502, True))

    def test_when_two_keys_fail_both_are_named_with_their_reason(self):
        out = ai_fallback.explain(self.attempts((GROUP, QuotaError("q", Quota(kind="billing"))), (OWN, ProviderError("x", failure.DENIED))))
        self.assertEqual(out.status_code, 502)
        self.assertIn("la clave del grupo se ha quedado sin saldo", out.detail)
        self.assertIn("tu clave de OpenAI no es aceptada por OpenAI", out.detail)
        out = ai_fallback.explain(self.attempts((GROUP, ProviderError("x", failure.DENIED)), (OWN, QuotaError("q", Quota(kind="day", retry_after=7200)))))
        self.assertEqual(out.status_code, 429)
        self.assertEqual(out.headers, {"Retry-After": "7200"})
        self.assertIn("la clave del grupo no es aceptada por el proveedor", out.detail)

    def test_every_key_of_a_player_is_named_when_they_all_fail(self):
        out = ai_fallback.explain(self.attempts((OWN, QuotaError("q", Quota(kind="billing"))), (OTHER, QuotaError("q", Quota(kind="billing")))))
        self.assertIn("tu clave de OpenAI", out.detail)
        self.assertIn("tu clave de Anthropic", out.detail)

    def test_no_key_and_no_text_of_the_provider_reaches_the_answer(self):
        error = QuotaError("chat: secret-provider-text", Quota(kind="billing", message="secret-provider-text", ids=("secret-id",)))
        out = ai_fallback.explain(self.attempts((GROUP, error), (OWN, error)))
        for secret in ("secret-provider-text", "secret-id", KEY, "GROUPKEY"):
            self.assertNotIn(secret, out.detail)


class WhoIsTriedTests(unittest.TestCase):
    """`ai_source.decide` lists the keys of a question: which are behind the first, by mode."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)

    def decide(self, mode, keys=(), locked=False, group=True, feature="chat"):
        dek = None
        for provider, key in keys:
            dek = ai_env.give_key(self.db, 1, key, "gpt-5-mini" if provider == "openai" else "claude-haiku-5-5", provider)
        with patched(**{f"{feature}.key_source": mode, f"{feature}.enabled": True, "ai.openai.api_key": "GROUPKEY" if group else None}):
            return ai_source.decide(self.db, 1, feature, None if locked else dek)

    def test_group_then_user_keeps_the_players_keys_behind_the_groups(self):
        decision = self.decide("group_then_user", [("openai", KEY), ("anthropic", ANTHROPIC_KEY)])
        self.assertEqual([(s.key_source, s.provider) for s in decision.sources], [("group", "openai"), ("user", "openai"), ("user", "anthropic")])

    def test_at_most_two_of_the_players_keys_are_tried(self):
        decision = self.decide("group_then_user", [("openai", KEY), ("anthropic", ANTHROPIC_KEY)])
        self.assertLessEqual(len(decision.fallback), ai_source.MAX_OWN_KEYS)

    def test_group_only_never_has_anything_behind_the_groups_key(self):
        decision = self.decide("group_only", [("openai", KEY)])
        self.assertEqual([s.key_source for s in decision.sources], ["group"])
        self.assertFalse(decision.fallback_locked)

    def test_user_only_never_has_the_groups_key_and_goes_through_their_own(self):
        decision = self.decide("user_only", [("openai", KEY), ("anthropic", ANTHROPIC_KEY)])
        self.assertEqual([(s.key_source, s.provider) for s in decision.sources], [("user", "openai"), ("user", "anthropic")])

    def test_without_keys_there_is_nothing_behind_the_group_and_a_locked_session_says_so(self):
        decision = self.decide("group_then_user")
        self.assertEqual((len(decision.sources), decision.fallback_locked), (1, False))
        decision = self.decide("group_then_user", [("openai", KEY)], locked=True)
        self.assertEqual((len(decision.sources), decision.fallback_locked), (1, True))

    def test_a_spent_budget_still_goes_straight_to_their_own_key(self):
        with mock.patch.object(ai_source.ai_budget, "exceeded", return_value="user"):
            decision = self.decide("group_then_user", [("openai", KEY)])
        self.assertEqual([s.key_source for s in decision.sources], ["user"])
        self.assertEqual(decision.blocked, "user")

    def test_a_locked_player_with_a_spent_budget_is_told_to_unlock_instead_of_to_save_a_key(self):
        with patched(**{"chat.key_source": "group_then_user"}):
            text = ai_source.blocked_message("user", "chat", locked=True)
        self.assertIn(messages.OWN_KEY_LOCKED, text)
        self.assertNotIn(messages.OWN_KEY_WAY_OUT, text)
        with patched(**{"chat.key_source": "group_only"}):
            self.assertEqual(ai_source.blocked_message("user", "chat", locked=True), messages.USER_BUDGET_REACHED)


class QuestionTests(unittest.TestCase):
    """A real question to the chat, end to end: the models are scripted by whose key they are called with."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.user = self.db.get(models.User, 1)
        chat_limits.limiter.clear()
        self.addCleanup(chat_limits.limiter.clear)
        self.called = []
        self.models = {}

    def answers(self, text="Hola"):
        def reply(history, info):
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"in_scope": True, "answer": text})])
        return FunctionModel(reply)

    def run_question(self, mode="group_then_user", keys=(), locked=False, group=None, own=None, other=None):
        """Asks "hola" with the group's key behaving as `group` (None answers) and the players' as `own` / `other`."""
        by_key = {"GROUPKEY": group, KEY: own, ANTHROPIC_KEY: other}
        dek = None
        for provider, key in keys:
            dek = ai_env.give_key(self.db, 1, key, "gpt-5-mini" if provider == "openai" else "claude-haiku-5-5", provider)

        def model_for(use, source=None):
            self.called.append(source.api_key)
            error = by_key[source.api_key]
            return ai_env.fails(error) if error else self.answers()

        with patched(**{"chat.key_source": mode, "chat.enabled": True, "chat.prompt": "Eres un bot.", "ai.openai.api_key": "GROUPKEY"}), \
                mock.patch.object(ai_build, "model_for", side_effect=model_for), \
                mock.patch.object(ai_quota, "report"), \
                self.assertLogs(level="DEBUG"):
            try:
                return chat_router.ask(chat_router.ChatRequest(message="hola"), current_user=self.user, dek=None if locked else dek, db=self.db)
            except HTTPException as e:
                return e

    def rows(self):
        return [(r.key_source, r.provider, r.status) for r in self.db.query(models.AiUsage).order_by(models.AiUsage.id).all()]

    def test_the_group_has_no_balance_and_the_players_own_key_answers(self):
        out = self.run_question(keys=[("openai", KEY)], group=billing())
        self.assertEqual(out.answer, "Hola")
        self.assertEqual(self.called, ["GROUPKEY", KEY])
        self.assertEqual(self.rows(), [("group", "openai", ai_ledger.QUOTA), ("user", "openai", ai_ledger.OK)])

    def test_the_groups_key_is_refused_and_the_players_own_key_answers(self):
        out = self.run_question(keys=[("openai", KEY)], group=refused())
        self.assertEqual(out.answer, "Hola")
        self.assertEqual(self.rows(), [("group", "openai", ai_ledger.ERROR), ("user", "openai", ai_ledger.OK)])

    def test_the_groups_daily_quota_also_goes_on_with_their_own_key(self):
        daily = ModelHTTPError(429, "m", {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})
        self.assertEqual(self.run_question(keys=[("openai", KEY)], group=daily).answer, "Hola")

    def test_a_rate_limit_of_the_group_passes_in_seconds_so_it_does_not_bill_their_account(self):
        out = self.run_question(keys=[("openai", KEY)], group=rate_limit())
        self.assertEqual(out.status_code, 429)
        self.assertEqual(self.called, ["GROUPKEY"])
        self.assertFalse(out.detail.endswith(messages.OWN_KEY_WAY_OUT))  # waiting is the way out, not their key

    def test_when_the_groups_key_answers_the_players_is_never_called(self):
        out = self.run_question(keys=[("openai", KEY)])
        self.assertEqual((out.answer, self.called, self.rows()), ("Hola", ["GROUPKEY"], [("group", "openai", ai_ledger.OK)]))

    def test_both_fail_and_the_player_is_told_what_happened_to_each(self):
        out = self.run_question(keys=[("openai", KEY)], group=billing(), own=billing())
        self.assertEqual(out.status_code, 429)
        self.assertIn("la clave del grupo se ha quedado sin saldo", out.detail)
        self.assertIn("tu clave de OpenAI se ha quedado sin saldo", out.detail)
        self.assertEqual(self.rows(), [("group", "openai", ai_ledger.QUOTA), ("user", "openai", ai_ledger.QUOTA)])

    def test_their_second_key_is_tried_when_the_first_fails(self):
        out = self.run_question(keys=[("openai", KEY), ("anthropic", ANTHROPIC_KEY)], group=billing(), own=refused())
        self.assertEqual(out.answer, "Hola")
        self.assertEqual(self.called, ["GROUPKEY", KEY, ANTHROPIC_KEY])
        self.assertEqual(self.rows(), [("group", "openai", ai_ledger.QUOTA), ("user", "openai", ai_ledger.ERROR), ("user", "anthropic", ai_ledger.OK)])

    def test_a_slow_group_provider_does_not_spend_the_players_account(self):
        out = self.run_question(keys=[("openai", KEY)], group=overloaded())
        self.assertEqual((out.status_code, out.detail), (502, messages.CHAT_OVERLOADED))
        self.assertEqual(self.called, ["GROUPKEY"])

    def test_a_group_failure_without_a_reason_does_not_spend_the_players_account_either(self):
        out = self.run_question(keys=[("openai", KEY)], group=bad_request())
        self.assertEqual((out.status_code, out.detail), (502, messages.CHAT_FAILED))
        self.assertEqual(self.called, ["GROUPKEY"])

    def test_group_only_ignores_their_key_and_does_not_offer_it(self):
        out = self.run_question(mode="group_only", keys=[("openai", KEY)], group=billing())
        self.assertEqual((out.status_code, out.detail), (429, messages.CHAT_QUOTA.format(when="")))
        self.assertEqual(self.called, ["GROUPKEY"])

    def test_without_a_key_of_their_own_they_are_told_they_can_save_one(self):
        out = self.run_question(group=billing())
        self.assertEqual((out.status_code, out.detail), (429, messages.CHAT_QUOTA.format(when="") + messages.OWN_KEY_WAY_OUT))

    def test_with_locked_keys_they_are_told_to_unlock_them_and_nothing_is_spent(self):
        out = self.run_question(keys=[("openai", KEY)], locked=True, group=billing())
        self.assertEqual(out.status_code, 429)
        self.assertTrue(out.detail.endswith(messages.OWN_KEY_LOCKED))
        self.assertEqual(self.called, ["GROUPKEY"])

    def test_user_only_goes_through_their_keys_and_never_the_groups(self):
        out = self.run_question(mode="user_only", keys=[("openai", KEY), ("anthropic", ANTHROPIC_KEY)], own=billing())
        self.assertEqual(out.answer, "Hola")
        self.assertEqual(self.called, [KEY, ANTHROPIC_KEY])

    def test_user_only_with_a_failing_key_says_it_is_theirs(self):
        out = self.run_question(mode="user_only", keys=[("openai", KEY)], own=refused())
        self.assertEqual(out.status_code, 502)
        self.assertTrue(out.detail.startswith("Tu clave de OpenAI no es aceptada"))

    def test_the_fallback_counts_the_question_once_for_the_limits(self):
        with mock.patch.object(chat_router.limits.limiter, "acquire", wraps=chat_router.limits.limiter.acquire) as acquire:
            self.run_question(keys=[("openai", KEY)], group=billing())
        self.assertEqual(acquire.call_count, 1)

    def test_a_locked_player_who_is_stopped_before_the_call_is_told_to_unlock_not_to_save_a_key(self):
        with patched(**{"chat.key_source": "group_then_user"}),                 mock.patch.object(ai_source, "decide", return_value=ai_source.Decision(None, "wallet", locked=True)):
            with self.assertRaises(HTTPException) as caught:
                chat_router.ask(chat_router.ChatRequest(message="hola"), current_user=self.user, dek=None, db=self.db)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail, messages.WALLET_EMPTY + messages.OWN_KEY_LOCKED)

    def test_no_key_reaches_the_answer_the_log_or_the_record(self):
        out = self.run_question(keys=[("openai", KEY)], group=billing(), own=refused())
        for text in (out.detail, repr(self.rows())):
            self.assertNotIn(KEY, text)
            self.assertNotIn("GROUPKEY", text)


class GuideQuestionTests(unittest.TestCase):
    """The same through the guide, which builds its deps for each key."""

    def setUp(self):
        self.db = make_session()
        seed(self.db)
        ai_env.free_wallet(self.db)
        self.user = self.db.get(models.User, 1)
        guide_limits.limiter.clear()
        self.addCleanup(guide_limits.limiter.clear)

    def ask(self, group, own, keys=((("openai", KEY)),)):
        dek = None
        for provider, key in keys:
            dek = ai_env.give_key(self.db, 1, key, "gpt-5-mini", provider)
        called = []

        def model_for(use, source=None):
            called.append(source.key_source)
            error = {"group": group, "user": own}[source.key_source]
            return ai_env.fails(error) if error else ai_env.says("Pásate por el mapa")

        with patched(**{"guide.key_source": "group_then_user", "guide.enabled": True, "guide.prompt": "Guía", "ai.openai.api_key": "GROUPKEY"}), \
                mock.patch.object(ai_build, "model_for", side_effect=model_for), \
                mock.patch.object(ai_quota, "report"), \
                mock.patch.object(guide_router.game_overview, "overview", return_value={"game": {"name": "Hollow Knight"}}), \
                mock.patch.object(guide_router.agent, "game_context", return_value="Juego: Hollow Knight"), \
                self.assertLogs(level="DEBUG"):
            try:
                return guide_router.ask("g1", guide_router.GuideRequest(message="hola"), current_user=self.user, dek=dek, db=self.db), called
            except HTTPException as e:
                return e, called

    def test_the_players_own_key_takes_over_when_the_groups_has_no_balance(self):
        out, called = self.ask(billing(), None)
        self.assertEqual((out.answer, called), ("Pásate por el mapa", ["group", "user"]))
        rows = [(r.key_source, r.status, r.game_id) for r in self.db.query(models.AiUsage).order_by(models.AiUsage.id).all()]
        self.assertEqual(rows, [("group", ai_ledger.QUOTA, "g1"), ("user", ai_ledger.OK, "g1")])

    def test_both_failing_says_what_happened_to_each(self):
        out, called = self.ask(refused(), billing())
        self.assertEqual((out.status_code, called), (429, ["group", "user"]))
        self.assertIn("la clave del grupo no es aceptada por el proveedor", out.detail)
        self.assertIn("tu clave de OpenAI se ha quedado sin saldo", out.detail)

    def test_a_timeout_of_the_group_stops_there(self):
        out, called = self.ask(ModelHTTPError(504, "m", {"error": {}}), None)
        self.assertEqual((out.status_code, out.detail, called), (504, messages.CHAT_TIMEOUT, ["group"]))


if __name__ == "__main__":
    unittest.main()

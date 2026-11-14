"""When the AI runs out of quota: what is recognized as such, what is written to the audit log and what each caller says."""
import contextlib
import types
import unittest
from unittest import mock

import httpx2
import openai
from fastapi import HTTPException
from google.genai import errors as google_errors
from pydantic_ai.exceptions import ModelHTTPError

from src.chat import limits as chat_limits
from src.chat import agent
from src.clients import quota
from src.clients.ai_error import AIError, Quota, QuotaError
from src.database import models
from src.routers import chat as chat_router
from src.routers.manage import system
from src.utils import ai, ai_quota, audit, messages, settings, ai_source
from tests import ai_env
from tests.sqlite_db import make_session


# `ai.complete` writes the record of a notice in a session of its own, which these tests have no database for
_no_record = mock.patch.object(ai.ai_ledger, "record_notice")


def setUpModule():
    _no_record.start()


def tearDownModule():
    _no_record.stop()

DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE = "GenerateContentInputTokensPerModelPerMinute-FreeTier"


def google_429(quota_id=DAY, value="20", retry="34s", message="You exceeded your current quota"):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", "quotaId": quota_id,
         "quotaDimensions": {"model": "gemini-test"}, "quotaValue": value}]}]
    if retry:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry})
    return google_errors.ClientError(429, {"error": {"code": 429, "message": message, "status": "RESOURCE_EXHAUSTED", "details": details}})


def openai_429(code, headers=None):
    response = httpx2.Response(429, request=httpx2.Request("POST", "https://api.example.com"), headers=headers or {})
    return openai.RateLimitError("limit", response=response, body={"message": "You exceeded your quota", "type": "x", "code": code})


class ClassifyTests(unittest.TestCase):
    def test_a_google_daily_quota_says_which_one_its_limit_and_when_to_retry(self):
        found = quota.classify(google_429())
        self.assertEqual((found.kind, found.ids, found.limit, found.retry_after), ("day", (DAY,), "20", 34))
        self.assertEqual(found.message, "You exceeded your current quota")

    def test_a_per_minute_quota_is_told_apart_and_the_retry_delay_is_rounded_up(self):
        found = quota.classify(google_429(MINUTE, "250000", "12.2s"))
        self.assertEqual((found.kind, found.retry_after), ("minute", 13))

    def test_without_details_it_is_still_a_quota_with_what_there_is(self):
        found = quota.classify(google_errors.ClientError(429, {"error": {"message": "slow down", "status": "RESOURCE_EXHAUSTED"}}))
        self.assertEqual((found.kind, found.ids, found.retry_after, found.message), ("unknown", (), None, "slow down"))

    def test_an_unexpected_body_never_raises(self):
        for body in (None, "text", [], {"error": "x"}, {"error": {"details": ["x", {"@type": 1}, {"@type": "QuotaFailure", "violations": [3]}]}}):
            self.assertIsInstance(quota.classify(google_errors.ClientError(429, body)), Quota)

    def test_openai_tells_the_billing_from_the_rate_and_reads_retry_after(self):
        self.assertEqual(quota.classify(openai_429("insufficient_quota")).kind, "billing")
        found = quota.classify(openai_429("rate_limit_exceeded", {"retry-after": "7"}))
        self.assertEqual((found.kind, found.retry_after), ("unknown", 7))

    def test_pydantic_ai_wraps_it_and_the_chain_is_followed(self):
        wrapped = ModelHTTPError(429, "m", {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "5s"}]}})
        self.assertEqual(quota.classify(wrapped).retry_after, 5)
        outer = RuntimeError("failed")
        outer.__cause__ = google_429()
        self.assertEqual(quota.classify(outer).kind, "day")

    def test_other_errors_are_not_a_quota(self):
        self.assertIsNone(quota.classify(RuntimeError("boom")))
        self.assertIsNone(quota.classify(google_errors.ClientError(403, {"error": {"message": "no"}})))
        self.assertIsNone(quota.classify(ModelHTTPError(500, "m", None)))

    def test_it_is_described_for_a_person(self):
        text = Quota("day", 34, (DAY,), "20").describe()
        self.assertEqual(text, f"Cupo de la IA agotado por día ({DAY}, límite 20). Reintenta en 34 s")
        self.assertEqual(Quota().describe(), "Cupo de la IA agotado")
        self.assertIn("5 min", Quota(retry_after=300).describe())
        self.assertIn("3 h", Quota(retry_after=3 * 3600).describe())


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        patcher = mock.patch.object(ai_quota, "SessionLocal", lambda: contextlib.nullcontext(self.db))
        patcher.start()
        self.addCleanup(patcher.stop)
        ai_quota._last.clear()
        self.addCleanup(ai_quota._last.clear)

    def rows(self):
        return [audit.entry_out(r) for r in self.db.query(models.AuditLog).order_by(models.AuditLog.id)]

    def test_a_refusal_is_one_event_row_with_who_asked_and_which_quota(self):
        self.assertTrue(ai_quota.report(Quota("day", 34, (DAY,), "20", "msg"), "chat", "google", "gemini-test", now=0))
        (row,) = self.rows()
        self.assertEqual((row["event"], row["username"], row["status"], row["entity"], row["path"]), ("ai_quota", "sistema", 429, "ai", "ai/chat"))
        self.assertEqual(row["detail"]["source"], "chat")
        self.assertEqual((row["detail"]["provider"], row["detail"]["model"], row["detail"]["kind"]), ("google", "gemini-test", "day"))
        self.assertEqual((row["detail"]["quotas"], row["detail"]["limit"], row["detail"]["retry_after"]), ([DAY], "20", 34))

    def test_the_same_quota_is_written_once_per_window_and_the_next_row_counts_the_repeats(self):
        found = Quota("day", None, (DAY,))
        self.assertTrue(ai_quota.report(found, "chat", "google", "m", now=0))
        self.assertFalse(ai_quota.report(found, "welcome", "google", "m", now=10))
        self.assertFalse(ai_quota.report(found, "chat", "google", "m", now=ai_quota.DEDUP_SECONDS - 1))
        self.assertTrue(ai_quota.report(found, "chat", "google", "m", now=ai_quota.DEDUP_SECONDS))
        self.assertEqual([r["detail"]["repeated"] for r in self.rows()], [0, 2])

    def test_another_quota_or_model_is_its_own_event(self):
        self.assertTrue(ai_quota.report(Quota("day", None, (DAY,)), "chat", "google", "a", now=0))
        self.assertTrue(ai_quota.report(Quota("minute", None, (MINUTE,)), "chat", "google", "a", now=1))
        self.assertTrue(ai_quota.report(Quota("day", None, (DAY,)), "chat", "google", "b", now=2))
        self.assertEqual(len(self.rows()), 3)

    def test_a_failure_writing_it_is_swallowed(self):
        with mock.patch.object(ai_quota, "SessionLocal", side_effect=RuntimeError("db down")):
            self.assertTrue(ai_quota.report(Quota(), "chat", "google", "m", now=0))


class CallersTests(unittest.TestCase):
    def setUp(self):
        ai_quota._last.clear()
        self.addCleanup(ai_quota._last.clear)
        patcher = mock.patch.object(ai_quota, "report")
        self.report = patcher.start()
        self.addCleanup(patcher.stop)

    def settings(self):
        base = {"ai.enabled": True, **ai_env.group("google", "KEY", "gemini-test"), "chat.prompt": "p"}
        return mock.patch.object(ai.settings, "get", side_effect=lambda key: base[key])

    def test_a_notice_that_hits_the_quota_is_reported_with_its_source_and_raises(self):
        with self.settings(), ai_env.using(ai_env.fails(google_429())), self.assertRaises(QuotaError):
            ai.complete("s", "u", source="notice:new_game")
        quota_arg, source, provider, model = self.report.call_args.args
        self.assertEqual((source, provider, model, quota_arg.kind), ("notice:new_game", "google", "gemini-test", "day"))

    def test_a_429_of_a_library_that_is_not_wrapped_is_recognized_too(self):
        with self.settings(), ai_env.using(ai_env.fails(openai_429("insufficient_quota"))), self.assertRaises(QuotaError) as caught:
            ai.complete("s", "u")
        self.assertEqual(caught.exception.quota.kind, "billing")
        self.assertEqual(self.report.call_args.args[1], "notice")

    def test_other_failures_are_not_reported(self):
        with self.settings(), ai_env.using(ai_env.fails(RuntimeError("boom"))), self.assertRaises(AIError) as caught:
            ai.complete("s", "u")
        self.assertNotIsInstance(caught.exception, QuotaError)
        self.report.assert_not_called()

    def test_the_chat_reports_it_and_says_so(self):
        with mock.patch.object(agent.settings, "get", side_effect=lambda key: ai_env.group("google", "KEY", "gemini-test")[key]):
            error = agent.failure(ModelHTTPError(429, "gemini-test", {"error": {"message": "q"}}), "chat")
        self.assertIsInstance(error, QuotaError)
        self.assertEqual(self.report.call_args.args[1:], ("chat", "google", "gemini-test"))


class AnswersTests(unittest.TestCase):
    admin = types.SimpleNamespace(username="root", id=1)

    def test_the_chat_endpoint_answers_429_with_a_friendly_message_and_the_wait(self):
        chat_limits.limiter.clear()
        self.addCleanup(chat_limits.limiter.clear)
        user = types.SimpleNamespace(id=7)
        failing = mock.Mock(side_effect=QuotaError("q", Quota("day", 90, (DAY,))))
        with mock.patch.object(chat_router.ai_source, "decide", return_value=ai_source.Decision(ai_source.Source("group", "openai", "KEY", "m"))), mock.patch.object(chat_router.agent, "ask", failing), \
                mock.patch.object(settings, "get", return_value=0):
            with self.assertRaises(HTTPException) as caught:
                chat_router.ask(chat_router.ChatRequest(message="hola"), current_user=user, db=mock.Mock())
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail, messages.CHAT_QUOTA.format(when=" (reintenta en 2 min)"))
        self.assertEqual(caught.exception.headers, {"Retry-After": "90"})

    def test_without_a_known_wait_the_message_has_none(self):
        chat_limits.limiter.clear()
        self.addCleanup(chat_limits.limiter.clear)
        failing = mock.Mock(side_effect=QuotaError("q", Quota()))
        with mock.patch.object(chat_router.ai_source, "decide", return_value=ai_source.Decision(ai_source.Source("group", "openai", "KEY", "m"))), mock.patch.object(chat_router.agent, "ask", failing), \
                mock.patch.object(settings, "get", return_value=0):
            with self.assertRaises(HTTPException) as caught:
                chat_router.ask(chat_router.ChatRequest(message="hola"), current_user=types.SimpleNamespace(id=8), db=mock.Mock())
        self.assertEqual(caught.exception.detail, messages.CHAT_QUOTA.format(when=""))
        self.assertIsNone(caught.exception.headers)

    def test_the_test_buttons_say_which_quota_ran_out(self):
        found = Quota("day", 34, (DAY,), "20")
        with mock.patch.object(system.settings, "get", return_value="x"), mock.patch.object(system.ai, "current", return_value=("google", "m")), \
                mock.patch.object(system.ai, "complete", side_effect=QuotaError("q", found)):
            with self.assertRaises(HTTPException) as caught:
                system.test_ai(self.admin)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (429, found.describe()))
        with mock.patch.object(system.chat_model, "configured", return_value=True), mock.patch.object(system.chat_agent, "probe", side_effect=QuotaError("q", found)):
            with self.assertRaises(HTTPException) as caught:
                system.test_chat(self.admin)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (429, found.describe()))


if __name__ == "__main__":
    unittest.main()


class RealBodiesTests(unittest.TestCase):
    """What the providers really answered when an account had nothing left (read from the real APIs, keys aside)."""

    def test_openai_with_no_credits_is_billing_even_though_its_code_is_not_the_old_one(self):
        body = {"message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.",
                "type": "insufficient_quota", "param": None, "code": "credit_balance_exhausted"}
        found = quota.classify(ModelHTTPError(429, "gpt-4.1-mini", body))
        self.assertEqual(found.kind, "billing")
        self.assertIn("no credits remaining", found.message)

    def test_the_old_code_and_a_type_alone_are_billing_too_and_a_plain_rate_limit_is_not(self):
        self.assertEqual(quota.classify(ModelHTTPError(429, "m", {"error": {"code": "insufficient_quota"}})).kind, "billing")
        self.assertEqual(quota.classify(ModelHTTPError(429, "m", {"error": {"type": "insufficient_quota"}})).kind, "billing")
        self.assertEqual(quota.classify(ModelHTTPError(429, "m", {"error": {"code": "rate_limit_exceeded"}})).kind, "unknown")

    def test_a_failure_says_which_feature_it_was(self):
        from src.guide import agent as guide_agent  # noqa: F401  (the guide reports through the chat's `failure`)

        with mock.patch.object(agent.ai_providers, "current", return_value=("openai", "m")), mock.patch.object(agent.ai_quota, "report"):
            quota_error = agent.failure(ModelHTTPError(429, "m", {"error": {"code": "insufficient_quota"}}), "guide", feature="guide")
            other = agent.failure(RuntimeError("boom"), "guide", feature="guide")
        self.assertTrue(str(quota_error).startswith("guide:"))
        self.assertTrue(str(other).startswith("guide: RuntimeError"))
        self.assertTrue(str(agent.failure(RuntimeError("boom"), "chat")).startswith("chat: RuntimeError"))

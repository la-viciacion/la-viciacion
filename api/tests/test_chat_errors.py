"""What a player is told when the provider fails: a timeout, an overload, a bad day, a refusal, each with its own answer."""
import types
import unittest
from unittest import mock

from fastapi import HTTPException
from google.genai import errors as google_errors
from pydantic_ai.exceptions import ModelHTTPError, ModelOverloadedError, ModelRequestTimeout, ModelServerError, ModelTimeoutError

from src.chat import agent
from src.chat import limits as chat_limits
from src.clients import failure
from src.clients.ai_error import AIError, ProviderError
from src.routers import chat as chat_router
from src.utils import messages, settings


def http(status, category=None, body=None):
    return ModelHTTPError.for_category(category, status_code=status, model_name="gemini-3.6-flash", body=body or {"error": {"code": status}})


class KindTests(unittest.TestCase):
    def test_the_errors_of_the_log_are_a_timeout_and_an_overload(self):
        deadline = http(504, ModelServerError, {"error": {"code": 504, "message": "Deadline expired before operation could complete.", "status": "DEADLINE_EXCEEDED"}})
        busy = http(503, ModelOverloadedError, {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}})
        self.assertEqual(failure.kind(deadline), failure.TIMEOUT)
        self.assertEqual(failure.kind(busy), failure.OVERLOADED)

    def test_each_status_is_a_kind(self):
        for status, expected in ((408, "timeout"), (504, "timeout"), (503, "overloaded"), (529, "overloaded"), (500, "server"), (502, "server"),
                                 (401, "denied"), (403, "denied")):
            self.assertEqual(failure.kind(http(status)), expected, status)

    def test_a_timeout_of_our_own_or_of_the_transport_is_a_timeout(self):
        for exc in (ModelTimeoutError("m", "read timed out"), ModelRequestTimeout("m", 30), TimeoutError("slow")):
            self.assertEqual(failure.kind(exc), failure.TIMEOUT, type(exc).__name__)

    def test_the_libraries_own_errors_are_read_too_and_so_is_a_chain(self):
        self.assertEqual(failure.kind(google_errors.ServerError(503, {"error": {"status": "UNAVAILABLE"}})), failure.OVERLOADED)
        self.assertEqual(failure.kind(google_errors.ClientError(403, {"error": {"status": "PERMISSION_DENIED"}})), failure.DENIED)
        outer = RuntimeError("failed")
        outer.__cause__ = http(500)
        self.assertEqual(failure.kind(outer), failure.SERVER)

    def test_what_has_nothing_to_tell_is_none_and_the_quota_is_not_here(self):
        for exc in (RuntimeError("boom"), ValueError("x"), http(400), http(404), http(429)):
            self.assertIsNone(failure.kind(exc), repr(exc))


class FailureTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(settings, "get", return_value="KEY")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_failure_of_the_provider_keeps_its_kind_and_never_the_key(self):
        error = agent.failure(http(504, ModelServerError, {"error": {"message": "token KEY rejected"}}), "chat")
        self.assertIsInstance(error, ProviderError)
        self.assertEqual(error.kind, failure.TIMEOUT)
        self.assertNotIn("KEY", str(error))
        self.assertIn("504", str(error))

    def test_anything_else_stays_a_plain_ai_error(self):
        error = agent.failure(RuntimeError("boom"), "chat")
        self.assertIs(type(error), AIError)


class AnswersTests(unittest.TestCase):
    user = types.SimpleNamespace(id=9)

    def setUp(self):
        chat_limits.limiter.clear()
        self.addCleanup(chat_limits.limiter.clear)

    def ask(self, error):
        with mock.patch.object(chat_router.chat_model, "is_ready", return_value=True), \
                mock.patch.object(chat_router.agent, "ask", side_effect=error), \
                mock.patch.object(settings, "get", return_value=0):
            with self.assertRaises(HTTPException) as caught:
                chat_router.ask(chat_router.ChatRequest(message="hola"), current_user=self.user, db=mock.Mock())
        return caught.exception

    def test_each_kind_gets_its_own_answer(self):
        for kind, status, message in (
            (failure.TIMEOUT, 504, messages.CHAT_TIMEOUT),
            (failure.OVERLOADED, 502, messages.CHAT_OVERLOADED),
            (failure.SERVER, 502, messages.CHAT_SERVER),
            (failure.DENIED, 502, messages.CHAT_DENIED),
        ):
            with self.assertLogs(chat_router.logger):
                refused = self.ask(ProviderError("chat: x", kind))
            self.assertEqual((refused.status_code, refused.detail), (status, message), kind)

    def test_a_failure_with_nothing_to_tell_gets_the_general_answer(self):
        with self.assertLogs(chat_router.logger):
            refused = self.ask(AIError("chat: boom"))
        self.assertEqual((refused.status_code, refused.detail), (502, messages.CHAT_FAILED))

    def test_never_a_503_for_the_provider_because_the_front_reads_it_as_the_chat_being_switched_off(self):
        for kind in (failure.TIMEOUT, failure.OVERLOADED, failure.SERVER, failure.DENIED):
            with self.assertLogs(chat_router.logger):
                self.assertNotEqual(self.ask(ProviderError("chat: x", kind)).status_code, 503)

    def test_a_slow_or_overloaded_provider_is_a_warning_and_the_rest_an_error(self):
        for kind, level in ((failure.TIMEOUT, "WARNING"), (failure.OVERLOADED, "WARNING"), (failure.SERVER, "ERROR"), (failure.DENIED, "ERROR")):
            with self.assertLogs(chat_router.logger, "WARNING") as logged:
                self.ask(ProviderError("chat: x", kind))
            self.assertEqual(logged.records[0].levelname, level, kind)

    def test_the_answers_are_all_different_and_none_is_empty(self):
        texts = [messages.CHAT_FAILED, messages.CHAT_TIMEOUT, messages.CHAT_OVERLOADED, messages.CHAT_SERVER, messages.CHAT_DENIED, messages.CHAT_QUOTA]
        self.assertEqual(len(set(texts)), len(texts))
        self.assertTrue(all(len(text) > 30 for text in texts))
        self.assertIn("{when}", messages.CHAT_QUOTA)

    def test_no_answer_names_the_provider(self):
        for name in ("CHAT_FAILED", "CHAT_TIMEOUT", "CHAT_OVERLOADED", "CHAT_SERVER", "CHAT_DENIED", "CHAT_QUOTA"):
            for provider in ("google", "gemini", "openai", "gpt", "anthropic"):
                self.assertNotIn(provider, getattr(messages, name).lower(), f"{name} names {provider}")


if __name__ == "__main__":
    unittest.main()

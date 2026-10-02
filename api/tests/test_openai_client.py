"""The OpenAI client wrapper: what it asks for, what it does with an empty answer, and that it reuses the client."""
import unittest
from types import SimpleNamespace
from unittest import mock

from src.clients import open_ai
from src.clients.ai_error import AIError


def completion(text):
    choices = [] if text is None else [SimpleNamespace(message=SimpleNamespace(content=text))]
    return SimpleNamespace(choices=choices)


class GenerateTests(unittest.TestCase):
    def fake_client(self, reply):
        client = mock.Mock()
        client.chat.completions.create.return_value = reply
        return client

    def test_it_asks_with_the_system_and_the_user_prompt_and_returns_the_trimmed_text(self):
        client = self.fake_client(completion("  ¡Hola!  \n"))
        with mock.patch.object(open_ai, "_client", return_value=client) as factory:
            text = open_ai.generate("sk-key", "gpt-x", "be funny", "greet the group", 0.7)
        self.assertEqual(text, "¡Hola!")
        factory.assert_called_once_with("sk-key")
        client.chat.completions.create.assert_called_once_with(
            model="gpt-x", temperature=0.7,
            messages=[{"role": "system", "content": "be funny"}, {"role": "user", "content": "greet the group"}],
        )

    def test_an_empty_answer_is_an_error_with_a_message(self):
        replies = (completion(""), completion("   "), completion(None), SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]))
        for reply in replies:
            with self.subTest(reply=reply), mock.patch.object(open_ai, "_client", return_value=self.fake_client(reply)):
                with self.assertRaisesRegex(AIError, "sin texto"):
                    open_ai.generate("k", "m", "s", "u", 1.0)

    def test_the_client_is_built_once_per_key_with_a_short_timeout(self):
        open_ai._client.cache_clear()
        with mock.patch.object(open_ai, "OpenAI", side_effect=lambda **kwargs: object()) as constructor:
            first, again, other = open_ai._client("key-a"), open_ai._client("key-a"), open_ai._client("key-b")
        self.assertIs(first, again)
        self.assertIsNot(first, other)
        self.assertEqual(constructor.call_count, 2)
        constructor.assert_any_call(api_key="key-a", timeout=open_ai.TIMEOUT_SECONDS)
        self.assertLess(open_ai.TIMEOUT_SECONDS, 60)  # the library default is ten minutes
        open_ai._client.cache_clear()


if __name__ == "__main__":
    unittest.main()

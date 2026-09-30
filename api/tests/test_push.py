import base64
import unittest
from unittest import mock

from pywebpush import WebPushException

from src.utils import push


class PayloadTests(unittest.TestCase):
    def test_markdown_is_removed(self):
        self.assertEqual(push.plain_text("*Ana* ha subido \\(↑2\\) `x`_y_"), "Ana ha subido (↑2) xy")

    def test_first_line_is_the_title_and_the_rest_the_body(self):
        payload = push.build_payload("📣 Ranking 📣\n1. *Ana*: 3h\n2. Bob: 2h", tag="group")
        self.assertEqual(payload["title"], "📣 Ranking 📣")
        self.assertEqual(payload["body"], "1. Ana: 3h · 2. Bob: 2h")
        self.assertEqual(payload["tag"], "group")
        self.assertEqual(payload["url"], "/")

    def test_a_single_line_gets_the_app_name_as_title(self):
        payload = push.build_payload("Ana acaba de perder la racha de 12 días.")
        self.assertEqual(payload["title"], push.APP_NAME)
        self.assertEqual(payload["body"], "Ana acaba de perder la racha de 12 días.")

    def test_long_texts_are_shortened(self):
        payload = push.build_payload("T" * 300 + "\n" + "b" * 500)
        self.assertLessEqual(len(payload["title"]), push.TITLE_MAX)
        self.assertLessEqual(len(payload["body"]), push.BODY_MAX)
        self.assertTrue(payload["body"].endswith("…"))

    def test_empty_message(self):
        self.assertEqual(push.build_payload("  \n ")["title"], push.APP_NAME)


class KeysTests(unittest.TestCase):
    def test_public_key_is_an_uncompressed_p256_point_in_base64url(self):
        public, private = push.generate_vapid_keys()
        raw = base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
        self.assertEqual((len(raw), raw[0]), (65, 4))
        self.assertIn("PRIVATE KEY", private)

    def test_each_call_gives_new_keys(self):
        self.assertNotEqual(push.generate_vapid_keys()[0], push.generate_vapid_keys()[0])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        _, self.private = push.generate_vapid_keys()
        self.devices = [(1, "https://push.example/a", "p", "a"), (2, "https://push.example/b", "p", "a"), (3, "https://push.example/c", "p", "a")]

    def deliver(self, side_effect):
        with mock.patch.object(push, "webpush", side_effect=side_effect):
            return push._deliver(self.devices, {"title": "t"}, self.private, "mailto:a@b.c")

    @staticmethod
    def failure(status):
        response = mock.Mock(status_code=status)
        return WebPushException("boom", response=response)

    def test_counts_sent_expired_and_failed(self):
        sent, gone, failed = self.deliver([None, self.failure(410), self.failure(500)])
        self.assertEqual((sent, gone, failed), (1, [2], 1))

    def test_a_missing_subscription_is_reported_as_gone(self):
        self.assertEqual(self.deliver([self.failure(404), None, None]), (2, [1], 0))

    def test_an_unexpected_error_does_not_stop_the_others(self):
        self.assertEqual(self.deliver([RuntimeError("network"), None, None]), (2, [], 1))

    def test_the_payload_is_sent_as_json_with_the_contact_and_a_short_ttl(self):
        with mock.patch.object(push, "webpush") as sender:
            push._deliver(self.devices[:1], {"title": "t"}, self.private, "mailto:a@b.c")
        kwargs = sender.call_args.kwargs
        self.assertEqual(kwargs["data"], '{"title": "t"}')
        self.assertEqual(kwargs["vapid_claims"], {"sub": "mailto:a@b.c"})
        self.assertEqual(kwargs["ttl"], push.TTL_SECONDS)


class DisabledTests(unittest.TestCase):
    def test_nothing_is_sent_while_push_is_not_ready(self):
        with mock.patch.object(push, "is_ready", return_value=False), mock.patch.object(push, "_send") as send:
            import asyncio

            asyncio.run(push.notify_group("hola"))
            self.assertEqual(asyncio.run(push.notify_user(1, "hola")), (0, 0))
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

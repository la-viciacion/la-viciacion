import base64
import datetime
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


class AnnouncementTests(unittest.TestCase):
    def test_a_valid_announcement(self):
        payload = push.build_announcement("  Mantenimiento  ", "Esta noche a las 3", "#/profile", "https://img.example/a.png")
        self.assertEqual(payload, {"title": "Mantenimiento", "body": "Esta noche a las 3", "url": "#/profile", "tag": None, "image": "https://img.example/a.png"})

    def test_body_link_and_image_are_optional(self):
        payload = push.build_announcement("Hola")
        self.assertEqual((payload["body"], payload["url"], "image" in payload), ("", "/", False))

    def test_rejects_what_cannot_be_sent(self):
        bad = [
            dict(title="  "),
            dict(title="T" * (push.TITLE_MAX + 1)),
            dict(title="ok", body="b" * (push.ANNOUNCEMENT_BODY_MAX + 1)),
            dict(title="ok", url="https://evil.example/"),
            dict(title="ok", url="//evil.example"),
            dict(title="ok", url="javascript:alert(1)"),
            dict(title="ok", image="http://img.example/a.png"),
            dict(title="ok", image="data:image/png;base64,AAAA"),
        ]
        for kwargs in bad:
            with self.assertRaises(ValueError, msg=str(kwargs)):
                push.build_announcement(**kwargs)

    def test_the_payload_stays_far_below_the_web_push_limit(self):
        payload = push.build_announcement("T" * push.TITLE_MAX, "b" * push.ANNOUNCEMENT_BODY_MAX, "/", "https://x.example/" + "a" * 400)
        self.assertLess(len(__import__("json").dumps(payload).encode()), 4096)


class DeliverTests(unittest.TestCase):
    def deliver(self, audience, user_id=None):
        import asyncio

        captured = {"query": mock.MagicMock()}

        async def fake_send(selector, payload):
            selector(captured["query"])
            return 2, 0

        with mock.patch.object(push, "is_ready", return_value=True), mock.patch.object(push, "_send", fake_send):
            result = asyncio.run(push.deliver({"title": "t"}, audience, user_id))
        return result, captured

    def test_every_audience_is_filtered_differently(self):
        for audience in ("me", "user", "group"):
            result, captured = self.deliver(audience, 5)
            self.assertEqual(result, (2, 0))
            captured["query"].filter.assert_called_once()
        result, captured = self.deliver("all")
        captured["query"].filter.assert_not_called()

    def test_unknown_audience(self):
        import asyncio

        with mock.patch.object(push, "is_ready", return_value=True), self.assertRaises(ValueError):
            asyncio.run(push.deliver({"title": "t"}, "nobody"))

    def test_nothing_is_sent_when_push_is_not_ready(self):
        import asyncio

        with mock.patch.object(push, "is_ready", return_value=False):
            self.assertEqual(asyncio.run(push.deliver({"title": "t"}, "all")), (0, 0))


class EnsureKeysTests(unittest.TestCase):
    def run_ensure(self, stored):
        db = mock.MagicMock()
        db.query.return_value.delete.return_value = 3
        with mock.patch.object(push.settings, "get_all", return_value=stored), mock.patch.object(push.settings, "set_values") as store:
            created = push.ensure_vapid_keys(db)
        return created, store, db

    def test_keys_are_created_on_the_first_start(self):
        created, store, db = self.run_ensure({"push.vapid_public": None, "push.vapid_private": None})
        self.assertTrue(created)
        values = store.call_args.args[1]
        self.assertEqual(set(values), {"push.vapid_public", "push.vapid_private"})
        self.assertIn("PRIVATE KEY", values["push.vapid_private"])
        db.query.return_value.delete.assert_called_once()  # devices of the old keys are useless

    def test_existing_keys_are_left_alone(self):
        created, store, db = self.run_ensure({"push.vapid_public": "pub", "push.vapid_private": "priv"})
        self.assertFalse(created)
        store.assert_not_called()
        db.query.assert_not_called()

    def test_an_unreadable_private_key_is_replaced(self):
        created, _, _ = self.run_ensure({"push.vapid_public": "pub", "push.vapid_private": None})
        self.assertTrue(created)


class TimerNoticeTests(unittest.TestCase):
    start = datetime.datetime(2026, 10, 1, 21, 35)

    def test_elapsed_text(self):
        cases = {0: "Timer iniciado", 59: "Timer iniciado", 60: "1 min", 300: "5 min", 3540: "59 min", 3600: "1h 00min", 5100: "1h 25min", 36000: "10h 00min"}
        for seconds, text in cases.items():
            self.assertEqual(push.elapsed_text(seconds), text, seconds)

    def test_a_negative_elapsed_time_counts_as_just_started(self):
        self.assertEqual(push.elapsed_text(-30), "Timer iniciado")

    def test_the_payload_replaces_the_previous_one_and_makes_no_noise(self):
        payload = push.build_timer_payload("Hollow Knight", self.start, self.start + datetime.timedelta(minutes=85))
        self.assertEqual((payload["title"], payload["body"]), ("Hollow Knight", "1h 25min"))
        self.assertEqual((payload["tag"], payload["quiet"], payload["pinned"], payload["url"]), (push.TIMER_TAG, True, True, "/"))

    def test_the_stopped_payload_keeps_the_tag_and_says_how_long_it_was(self):
        payload = push.build_timer_stopped_payload("Hollow Knight", 5100)
        self.assertEqual((payload["tag"], payload["body"]), (push.TIMER_TAG, "Timer parado · 1h 25min"))
        self.assertNotIn("pinned", payload)
        self.assertEqual(push.build_timer_stopped_payload("x", None)["body"], "Timer parado")

    def test_a_long_game_name_is_shortened(self):
        payload = push.build_timer_payload("T" * 300, self.start, self.start)
        self.assertLessEqual(len(payload["title"]), push.TITLE_MAX)

    def test_the_payload_is_far_below_the_web_push_limit(self):
        payload = push.build_timer_payload("T" * push.TITLE_MAX, self.start, self.start)
        self.assertLess(len(__import__("json").dumps(payload).encode()), push.PAYLOAD_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()

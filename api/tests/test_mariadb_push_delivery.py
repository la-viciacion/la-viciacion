"""Web Push delivery (MariaDB required, see api_support.py): who a notice reaches, which devices are dropped
and what is counted as a failure. `webpush` is a recorder, so nothing leaves the process; the VAPID keys are real
because the delivery code loads them."""
import asyncio
import datetime
import json
from unittest import mock

from pywebpush import WebPushException
from sqlalchemy import text

from src.database import database
from src.utils import push
from tests.api_support import ApiTestCase


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class PushTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        with database.SessionLocal() as db:
            push.ensure_vapid_keys(db)
        self.set_settings(**{"push.enabled": True})
        self.pushed = []
        self.failures = {}  # endpoint -> exception to raise

        def webpush(info, data, vapid_private_key, vapid_claims, ttl, timeout):
            self.pushed.append({"endpoint": info["endpoint"], "data": json.loads(data), "claims": vapid_claims, "ttl": ttl})
            if info["endpoint"] in self.failures:
                raise self.failures[info["endpoint"]]

        patcher = mock.patch.object(push, "webpush", new=webpush)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ana, self.bea = self.user("ana"), self.user("bea")

    def device(self, user_id, endpoint, group=True):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, receive_group) VALUES (:u, :e, 'k', 'a', :g)"),
                         {"u": user_id, "e": endpoint, "g": int(group)})

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def endpoints(self):
        return sorted(p["endpoint"] for p in self.pushed)

    def remaining(self):
        return sorted(r[0] for r in self.rows("SELECT endpoint FROM push_subscriptions"))


class DeliverFunctionTests(PushTestCase):
    def deliver(self, devices):
        with database.SessionLocal() as db:
            private = push.settings.get_all(db)["push.vapid_private"]
        return push._deliver(devices, {"title": "T"}, private, "mailto:a@b.c", 60)

    def test_it_counts_what_was_sent_what_is_gone_and_what_failed(self):
        self.failures = {
            "https://p/gone-404": WebPushException("gone", response=Response(404)),
            "https://p/gone-410": WebPushException("gone", response=Response(410)),
            "https://p/rejected": WebPushException("bad", response=Response(500)),
            "https://p/no-response": WebPushException("timeout"),
            "https://p/crash": RuntimeError("boom"),
        }
        devices = [(1, "https://p/ok", "k", "a"), (2, "https://p/gone-404", "k", "a"), (3, "https://p/gone-410", "k", "a"),
                   (4, "https://p/rejected", "k", "a"), (5, "https://p/no-response", "k", "a"), (6, "https://p/crash", "k", "a")]
        self.assertEqual(self.deliver(devices), (1, [2, 3], 3))

    def test_the_payload_ttl_and_sender_contact_travel_with_every_push(self):
        self.deliver([(1, "https://p/ok", "k", "a")])
        self.assertEqual(self.pushed[0], {"endpoint": "https://p/ok", "data": {"title": "T"}, "claims": {"sub": "mailto:a@b.c"}, "ttl": 60})


class AudienceTests(PushTestCase):
    def setUp(self):
        super().setUp()
        self.device(self.ana, "https://p/ana-phone")
        self.device(self.ana, "https://p/ana-tablet", group=False)
        self.device(self.bea, "https://p/bea-phone")

    def deliver(self, audience, user_id=None):
        return self.run_async(push.deliver({"title": "T", "body": "B", "url": "/", "tag": None}, audience, user_id))

    def test_me_and_user_reach_only_that_user_s_devices(self):
        self.assertEqual(self.deliver("me", self.ana), (2, 0))
        self.assertEqual(self.endpoints(), ["https://p/ana-phone", "https://p/ana-tablet"])
        self.pushed.clear()
        self.assertEqual(self.deliver("user", self.bea), (1, 0))
        self.assertEqual(self.endpoints(), ["https://p/bea-phone"])

    def test_the_group_reaches_the_devices_that_want_group_notices(self):
        self.assertEqual(self.deliver("group"), (2, 0))
        self.assertEqual(self.endpoints(), ["https://p/ana-phone", "https://p/bea-phone"])

    def test_all_reaches_every_device(self):
        self.assertEqual(self.deliver("all"), (3, 0))

    def test_an_unknown_audience_is_refused(self):
        with self.assertRaises(ValueError):
            self.deliver("nobody")

    def test_a_disabled_account_gets_nothing(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_active = 0 WHERE id = :u"), {"u": self.bea})
        self.assertEqual(self.deliver("all"), (2, 0))
        self.assertNotIn("https://p/bea-phone", self.endpoints())

    def test_expired_subscriptions_are_removed_and_the_rest_counted(self):
        self.failures = {"https://p/ana-phone": WebPushException("gone", response=Response(410)),
                         "https://p/bea-phone": WebPushException("bad", response=Response(500))}
        self.assertEqual(self.deliver("all"), (1, 1))
        self.assertEqual(self.remaining(), ["https://p/ana-tablet", "https://p/bea-phone"])

    def test_nothing_is_sent_when_push_is_off(self):
        self.set_settings(**{"push.enabled": False})
        self.assertEqual(self.deliver("all"), (0, 0))
        self.assertEqual(self.pushed, [])

    def test_a_crash_while_sending_is_answered_not_raised(self):
        with mock.patch.object(push, "_send", side_effect=RuntimeError("db down")):
            self.assertEqual(self.deliver("all"), (0, 0))


class NoticeTests(PushTestCase):
    def setUp(self):
        super().setUp()
        self.device(self.ana, "https://p/ana-phone")
        self.device(self.bea, "https://p/bea-phone", group=False)

    def test_a_group_notice_goes_to_the_devices_that_want_it_with_the_first_line_as_title(self):
        self.run_async(push.notify_group("*Big news*\nSomething happened"))
        self.assertEqual(self.endpoints(), ["https://p/ana-phone"])
        data = self.pushed[0]["data"]
        self.assertEqual((data["title"], data["body"], data["tag"], self.pushed[0]["ttl"]), ("Big news", "Something happened", "group", push.TTL_SECONDS))

    def test_a_private_notice_goes_to_one_user_and_reports_the_counts(self):
        self.assertEqual(self.run_async(push.notify_user(self.bea, "Only you", tag="private")), (1, 0))
        self.assertEqual((self.endpoints(), self.pushed[0]["data"]["tag"]), (["https://p/bea-phone"], "private"))

    def test_nothing_happens_when_push_is_off(self):
        self.set_settings(**{"push.enabled": False})
        self.run_async(push.notify_group("x"))
        self.assertEqual(self.run_async(push.notify_user(self.ana, "x")), (0, 0))
        self.assertEqual(self.pushed, [])

    def test_the_running_timer_is_pinned_with_a_short_ttl(self):
        self.run_async(push.notify_timer(self.ana, "Celeste", datetime.datetime.now() - datetime.timedelta(minutes=12)))
        data = self.pushed[0]["data"]
        self.assertEqual((data["title"], data["body"], data["pinned"], data["tag"]), ("Celeste", "12 min", True, "timer"))
        self.assertEqual(self.pushed[0]["ttl"], push.TIMER_TTL_SECONDS)

    def test_a_stopped_timer_replaces_the_pinned_notification(self):
        self.run_async(push.notify_timer_stopped(self.ana, "Celeste", 3725))
        data = self.pushed[0]["data"]
        self.assertEqual((data["title"], data["body"], data["tag"]), ("Celeste", "Timer parado · 1h 02min", "timer"))
        self.assertNotIn("pinned", data)

    def test_a_failure_in_a_notice_is_logged_not_raised(self):
        with mock.patch.object(push, "_send", side_effect=RuntimeError("down")):
            self.run_async(push.notify_timer(self.ana, "Celeste", datetime.datetime.now()))
            self.run_async(push.notify_timer_stopped(self.ana, "Celeste", 60))
            self.run_async(push.notify_group("x"))
            self.assertEqual(self.run_async(push.notify_user(self.ana, "x")), (0, 0))


class ContactTests(PushTestCase):
    def contact(self, smtp="", public_url=""):
        with mock.patch.object(push.config, "SMTP_EMAIL", smtp), mock.patch.object(push.config, "PUBLIC_URL", public_url):
            return push.contact()

    def test_the_admin_s_setting_wins_then_the_sender_address_then_an_https_url(self):
        self.assertEqual(self.contact(), "mailto:admin@localhost")
        self.assertEqual(self.contact(public_url="http://insecure.example"), "mailto:admin@localhost")
        self.assertEqual(self.contact(public_url="https://la-viciacion.example"), "https://la-viciacion.example")
        self.assertEqual(self.contact(smtp="app@example.com", public_url="https://la-viciacion.example"), "mailto:app@example.com")
        self.set_settings(**{"push.contact": "mailto:chosen@example.com"})
        self.assertEqual(self.contact(smtp="app@example.com"), "mailto:chosen@example.com")

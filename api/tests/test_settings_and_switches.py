import types
import unittest
from unittest import mock

from src.utils import my_utils, settings


class CoerceTests(unittest.TestCase):
    def test_booleans(self):
        self.assertIs(settings.coerce("notifications.enabled", True), True)
        self.assertIs(settings.coerce("notifications.enabled", "false"), False)
        self.assertIs(settings.coerce("notifications.enabled", "1"), True)
        with self.assertRaises(ValueError):
            settings.coerce("notifications.enabled", "maybe")

    def test_weekday_and_time(self):
        self.assertEqual(settings.coerce("weekly.weekday", "6"), 6)
        for bad in (-1, 7, "x"):
            with self.assertRaises(ValueError):
                settings.coerce("weekly.weekday", bad)
        self.assertEqual(settings.coerce("weekly.time", "09:30"), "09:30")
        for bad in ("9:30", "24:00", "09:60", ""):
            with self.assertRaises(ValueError):
                settings.coerce("weekly.time", bad)

    def test_telegram_values(self):
        self.assertEqual(settings.coerce("telegram.group_id", "-1001234567890"), "-1001234567890")
        with self.assertRaises(ValueError):
            settings.coerce("telegram.group_id", "@canal")
        token = "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345"
        self.assertEqual(settings.coerce("telegram.token", f" {token} "), token)
        with self.assertRaises(ValueError):
            settings.coerce("telegram.token", "not-a-token")

    def test_unknown_key(self):
        with self.assertRaises(KeyError):
            settings.coerce("nope", 1)


class EncryptionTests(unittest.TestCase):
    def test_secret_is_encrypted_and_round_trips(self):
        token = "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345"
        stored = settings._encode("telegram.token", token)
        self.assertNotIn(token, stored)
        self.assertNotIn("AAE_", stored)
        self.assertEqual(settings._decode("telegram.token", stored), token)

    def test_plain_values_are_not_encrypted(self):
        self.assertEqual(settings._encode("weekly.time", "09:00"), "09:00")
        self.assertEqual(settings._encode("notifications.enabled", False), "0")
        self.assertIs(settings._decode("notifications.enabled", "1"), True)
        self.assertEqual(settings._decode("weekly.weekday", "3"), 3)

    def test_missing_value_uses_the_default(self):
        self.assertEqual(settings._decode("weekly.time", None), "09:00")
        self.assertIsNone(settings._decode("telegram.token", None))


class FakeBot:
    sent = []

    def __init__(self, token):
        self.token = token

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, **kwargs):
        FakeBot.sent.append(kwargs)


def fake_settings(values):
    return mock.patch.object(my_utils.settings, "get", side_effect=lambda key: values.get(key))


class SwitchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeBot.sent = []
        self.bot = mock.patch.object(my_utils.telegram, "Bot", FakeBot)
        self.bot.start()
        self.addCleanup(self.bot.stop)

    base = {
        "notifications.enabled": True,
        "notifications.admin_alerts": True,
        "telegram.token": "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345",
        "telegram.group_id": "-100",
    }

    async def test_enabled_sends_to_the_group(self):
        with fake_settings(self.base):
            await my_utils.send_message("hola", False)
        self.assertEqual([m["chat_id"] for m in FakeBot.sent], ["-100"])

    async def test_general_switch_off_sends_nothing_to_group_or_users(self):
        values = {**self.base, "notifications.enabled": False}
        with fake_settings(values):
            await my_utils.send_message("hola", False)
            await my_utils.send_message_to_user(42, "hola")
        self.assertEqual(FakeBot.sent, [])

    async def test_silent_still_sends_nothing(self):
        with fake_settings(self.base):
            await my_utils.send_message("hola", True)
        self.assertEqual(FakeBot.sent, [])

    async def test_user_without_telegram_id_is_skipped(self):
        with fake_settings(self.base):
            await my_utils.send_message_to_user(None, "hola")
        self.assertEqual(FakeBot.sent, [])

    async def test_admin_alerts_have_their_own_switch(self):
        admins = [types.SimpleNamespace(is_admin=1, telegram_id=7), types.SimpleNamespace(is_admin=1, telegram_id=None)]
        with mock.patch.object(my_utils.users, "get_users", return_value=admins):
            # general switch off does not silence admin alerts...
            with fake_settings({**self.base, "notifications.enabled": False}):
                await my_utils.send_message_to_admins(None, "error")
            self.assertEqual([m["chat_id"] for m in FakeBot.sent], [7])
            # ...their own switch does (and admins without a Telegram id are skipped)
            FakeBot.sent = []
            with fake_settings({**self.base, "notifications.admin_alerts": False}):
                await my_utils.send_message_to_admins(None, "error")
            self.assertEqual(FakeBot.sent, [])

    async def test_test_message_goes_to_the_group_even_with_notifications_off(self):
        with fake_settings({**self.base, "notifications.enabled": False}):
            await my_utils.send_test_message("admin")
        self.assertEqual(len(FakeBot.sent), 1)
        self.assertEqual(FakeBot.sent[0]["chat_id"], "-100")
        self.assertIn("admin", FakeBot.sent[0]["text"])

    async def test_test_message_without_configuration_explains_why(self):
        with fake_settings({"notifications.enabled": True}):
            with self.assertRaises(ValueError):
                await my_utils.send_test_message("admin")

    async def test_user_test_message_goes_to_that_chat_even_with_notifications_off(self):
        with fake_settings({**self.base, "notifications.enabled": False}):
            self.assertTrue(await my_utils.send_test_message_to_user(42))
        self.assertEqual([m["chat_id"] for m in FakeBot.sent], [42])

    async def test_missing_token_does_not_raise(self):
        with fake_settings({"notifications.enabled": True}):
            await my_utils.send_message("hola", False)
        self.assertEqual(FakeBot.sent, [])


if __name__ == "__main__":
    unittest.main()

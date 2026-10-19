import types
import unittest
from unittest import mock

from src.utils import my_utils, settings
from tests.sqlite_db import make_session


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

    def test_the_monthly_recap_goes_out_in_the_first_five_days(self):
        for good in (1, "3", 5):
            self.assertIn(settings.coerce("monthly.day", good), range(1, 6))
        for bad in (0, 6, 28, "x"):
            with self.assertRaises(ValueError):
                settings.coerce("monthly.day", bad)

    def test_the_annual_recap_is_off_and_in_january_by_default(self):
        self.assertEqual(
            [settings.REGISTRY[key].default for key in ("annual.enabled", "annual.month", "annual.day", "annual.time")],
            [False, 1, 1, "10:00"],
        )
        self.assertIsNone(settings.check_annual(settings.REGISTRY["annual.month"].default, settings.REGISTRY["annual.day"].default))

    def test_the_annual_month_is_december_or_january(self):
        self.assertEqual((settings.coerce("annual.month", "12"), settings.coerce("annual.month", 1)), (12, 1))
        for bad in (0, 2, 6, 11, 13):
            with self.assertRaises(ValueError):
                settings.coerce("annual.month", bad)

    def test_the_annual_day_goes_with_its_month(self):
        for month, good, bad in ((12, (20, 24, 28), (1, 19, 29)), (1, (1, 3, 5), (6, 20, 28))):
            for day in good:
                self.assertIsNone(settings.check_annual(month, day), (month, day))
            for day in bad:
                self.assertIsNotNone(settings.check_annual(month, day), (month, day))
        self.assertIn("entre el 20 y el 28", settings.check_annual(12, 5))
        self.assertIn("entre el 1 y el 5", settings.check_annual(1, 25))

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


class AnnualRecapStoreTests(unittest.TestCase):
    """The month and the day of the annual recap are checked together, with what is stored."""

    def setUp(self):
        self.db = make_session()

    def test_a_december_day_is_stored_with_its_month(self):
        changed = settings.set_values(self.db, {"annual.month": 12, "annual.day": 25})
        self.assertCountEqual(changed, ["annual.month", "annual.day"])

    def test_a_day_that_does_not_fit_the_month_stores_nothing(self):
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"annual.month": 12, "annual.day": 3, "annual.enabled": True})
        self.assertEqual(settings.get_all(self.db)["annual.enabled"], False)
        self.assertEqual(settings.get_all(self.db)["annual.month"], 1)

    def test_changing_only_the_month_must_still_fit_the_stored_day(self):
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"annual.month": 12})  # the day is the default, 1
        settings.set_values(self.db, {"annual.month": 12, "annual.day": 22})
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"annual.month": 1})  # the day is 22 now

    def test_changing_only_the_day_must_fit_the_stored_month(self):
        settings.set_values(self.db, {"annual.month": 12, "annual.day": 22})
        settings.set_values(self.db, {"annual.day": 27})
        with self.assertRaises(ValueError):
            settings.set_values(self.db, {"annual.day": 4})

    def test_other_settings_do_not_trigger_the_check(self):
        self.assertEqual(settings.set_values(self.db, {"monthly.day": 3}), ["monthly.day"])


class EncryptionTests(unittest.TestCase):
    def test_secret_is_encrypted_and_round_trips(self):
        key = "sk-AAE_abcdefghijklmnopqrstuvwxyz012345"
        stored = settings._encode("ai.api_key", key)
        self.assertNotIn(key, stored)
        self.assertNotIn("AAE_", stored)
        self.assertEqual(settings._decode("ai.api_key", stored), key)

    def test_plain_values_are_not_encrypted(self):
        self.assertEqual(settings._encode("weekly.time", "09:00"), "09:00")
        self.assertEqual(settings._encode("notifications.enabled", False), "0")
        self.assertIs(settings._decode("notifications.enabled", "1"), True)
        self.assertEqual(settings._decode("weekly.weekday", "3"), 3)

    def test_missing_value_uses_the_default(self):
        self.assertEqual(settings._decode("weekly.time", None), "09:00")
        self.assertIsNone(settings._decode("ai.api_key", None))


class EnvOnlyTests(unittest.TestCase):
    """The keys of outside services (the Telegram token and chats, the AI key) live in the environment: a copy of the
    database must not carry them. The AI provider and model are there too, with no default in the code (see utils/ai.py)."""

    KEYS = ("telegram.token", "telegram.group_id", "telegram.admin_chat_id", "ai.api_key", "ai.provider", "ai.model")

    def test_the_keys_of_outside_services_are_the_ones_that_are_env_only(self):
        self.assertEqual({key for key, spec in settings.REGISTRY.items() if spec.env_only}, set(self.KEYS))

    def test_they_are_read_from_the_environment_every_time(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_TOKEN": " 123456789:abc ", "TELEGRAM_GROUP_ID": "-100"}):
            self.assertEqual(settings.get("telegram.token"), "123456789:abc")
            self.assertEqual(settings.get("telegram.group_id"), "-100")
        with mock.patch.dict("os.environ", {"TELEGRAM_TOKEN": "", "TELEGRAM_GROUP_ID": "-200"}):
            self.assertIsNone(settings.get("telegram.token"))  # blank is not set
            self.assertEqual(settings.get("telegram.group_id"), "-200")  # no stale copy

    def test_they_never_touch_the_database(self):
        with mock.patch.object(settings, "SessionLocal", side_effect=AssertionError("the database was asked")),              mock.patch.dict("os.environ", {"TELEGRAM_TOKEN": "123456789:abc"}):
            settings.get("telegram.token")

    def test_they_cannot_be_written(self):
        for key in self.KEYS:
            with self.assertRaises(ValueError) as error:
                settings.set_values(mock.Mock(), {key: "1"})
            self.assertIn(".env", str(error.exception))


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

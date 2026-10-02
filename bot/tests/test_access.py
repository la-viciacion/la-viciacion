import unittest

from src.utils import access

GROUP = "-1001234567890"
USERS = [
    {"username": "ana", "telegram_id": 111, "is_active": 1},
    {"username": "luis", "telegram_id": None, "is_active": 1},
]


class ChatAllowedTests(unittest.TestCase):
    def test_private_chat_is_allowed(self):
        self.assertTrue(access.chat_allowed("private", 111, GROUP))

    def test_configured_group_is_allowed(self):
        self.assertTrue(access.chat_allowed("supergroup", -1001234567890, GROUP))
        self.assertTrue(access.chat_allowed("group", -1001234567890, GROUP))

    def test_other_group_is_refused(self):
        self.assertFalse(access.chat_allowed("supergroup", -100999, GROUP))

    def test_channel_is_refused_even_with_the_group_id(self):
        self.assertFalse(access.chat_allowed("channel", -1001234567890, GROUP))

    def test_unset_or_garbage_group_refuses_every_group(self):
        for group in (None, "", "abc"):
            self.assertFalse(access.chat_allowed("supergroup", -1001234567890, group))


class FindAppUserTests(unittest.TestCase):
    def test_matches_by_telegram_id(self):
        self.assertEqual(access.find_app_user(USERS, 111)["username"], "ana")

    def test_unknown_id(self):
        self.assertIsNone(access.find_app_user(USERS, 222))

    def test_accounts_without_telegram_id_never_match(self):
        self.assertIsNone(access.find_app_user(USERS, None))


class CommandOfTests(unittest.TestCase):
    def test_plain_and_addressed_commands(self):
        self.assertEqual(access.command_of("/menu"), "menu")
        self.assertEqual(access.command_of("/Activate@LaViciacionBot x"), "activate")

    def test_not_a_command(self):
        self.assertIsNone(access.command_of("hola"))
        self.assertIsNone(access.command_of(None))


class AddressedToTests(unittest.TestCase):
    def test_plain_command_and_own_name(self):
        self.assertTrue(access.addressed_to("/menu", "LaViciacionBot"))
        self.assertTrue(access.addressed_to("/menu@laviciacionbot x", "LaViciacionBot"))

    def test_other_bot(self):
        self.assertFalse(access.addressed_to("/start@OtherBot", "LaViciacionBot"))


class PlanActivationTests(unittest.TestCase):
    users = [
        {"id": 1, "username": "Ana", "telegram_id": 111, "is_active": 1},
        {"id": 2, "username": "Luis", "telegram_id": None, "is_active": 1},
        {"id": 3, "username": "Eva", "telegram_id": None, "is_active": 0},
        {"id": 4, "username": "Pau", "telegram_id": 444, "is_active": 1},
    ]

    def plan(self, telegram_id, username):
        return access.plan_activation(self.users, telegram_id, username)

    def test_links_the_account_with_the_same_username_ignoring_case(self):
        outcome, account = self.plan(222, "luis")
        self.assertEqual((outcome, account["id"]), (access.ACTIVATE_OK, 2))

    def test_already_linked_id(self):
        self.assertEqual(self.plan(111, "whatever")[0], access.ACTIVATE_ALREADY)

    def test_no_telegram_username(self):
        self.assertEqual(self.plan(222, None)[0], access.ACTIVATE_NO_USERNAME)

    def test_no_account_with_that_username(self):
        self.assertEqual(self.plan(222, "nadie")[0], access.ACTIVATE_NO_ACCOUNT)

    def test_inactive_account_is_not_linked(self):
        self.assertEqual(self.plan(333, "eva"), (access.ACTIVATE_INACTIVE, None))

    def test_account_with_another_id_is_never_overwritten(self):
        self.assertEqual(self.plan(555, "Pau"), (access.ACTIVATE_TAKEN, None))


if __name__ == "__main__":
    unittest.main()

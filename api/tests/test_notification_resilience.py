import types
import unittest
from unittest import mock

import telegram

from src.crud import users as users_crud
from src.utils import actions, my_utils


class PickyBot:
    """Rejects Markdown when `reject_markdown`, fails outright when `broken`."""

    def __init__(self, reject_markdown=False, broken=False):
        self.reject_markdown, self.broken, self.calls = reject_markdown, broken, []

    async def send_message(self, text, chat_id, parse_mode=None):
        self.calls.append(parse_mode)
        if self.broken:
            raise telegram.error.NetworkError("down")
        if self.reject_markdown and parse_mode is not None:
            raise telegram.error.BadRequest("Can't parse entities")


class TelegramSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_unparsable_markdown_is_resent_as_plain_text(self):
        bot = PickyBot(reject_markdown=True)
        self.assertTrue(await my_utils._telegram_send(bot, 1, "Half_Life *"))
        self.assertEqual(bot.calls, [telegram.constants.ParseMode.MARKDOWN, None])

    async def test_a_dead_network_is_retried_and_never_raises(self):
        bot = PickyBot(broken=True)
        self.assertFalse(await my_utils._telegram_send(bot, 1, "hola"))
        self.assertEqual(len(bot.calls), my_utils.TELEGRAM_RETRIES)

    async def test_a_rejected_plain_message_gives_up_without_raising(self):
        bot = PickyBot(reject_markdown=True)
        bot.send_message = mock.AsyncMock(side_effect=telegram.error.BadRequest("chat not found"))
        self.assertFalse(await my_utils._telegram_send(bot, 1, "hola"))
        self.assertEqual(bot.send_message.await_count, 2)


class EscapeMarkdownTests(unittest.TestCase):
    def test_formatting_characters_are_escaped(self):
        self.assertEqual(my_utils.escape_markdown("a_b*c[d`e"), "a\_b\*c\[d\`e")

    def test_plain_names_are_untouched(self):
        self.assertEqual(my_utils.escape_markdown("Toni Miquel"), "Toni Miquel")


class CheckUsersTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_failing_user_does_not_skip_the_rest(self):
        users = [types.SimpleNamespace(id=i, username=f"u{i}") for i in (1, 2, 3)]
        checked = []

        async def check_user(db, user, **kw):
            if user.id == 2:
                raise RuntimeError("boom")
            checked.append(user.id)

        db = mock.MagicMock()
        with mock.patch.object(actions.users, "get_users", return_value=users), \
                mock.patch.object(actions, "check_user", check_user), \
                mock.patch.object(actions.achievements, "populate_achievements"), \
                mock.patch.object(actions.achievements, "teamwork", new=mock.AsyncMock()) as teamwork, \
                mock.patch.object(actions.utils, "send_message_to_admins", new=mock.AsyncMock()) as alert:
            await actions.check_users(db)
        self.assertEqual(checked, [1, 3])
        teamwork.assert_awaited_once()
        db.rollback.assert_called_once()
        self.assertIn("u2", alert.await_args.args[1])


class NewGameAnnouncementTests(unittest.IsolatedAsyncioTestCase):
    async def announce(self, game, send):
        user = types.SimpleNamespace(id=1, name="Ana_B")
        with mock.patch.object(users_crud, "count_played_games", return_value=3), \
                mock.patch.object(users_crud.utils, "send_message", send):
            await users_crud._announce_new_game(None, user, game, __import__("datetime").date(2026, 1, 1), False)

    async def test_a_game_without_slug_is_announced_without_link(self):
        send = mock.AsyncMock()
        await self.announce(types.SimpleNamespace(name="Doom", slug=None), send)
        text = send.await_args.args[0]
        self.assertIn("Doom", text)
        self.assertNotIn("rawg.io", text)
        self.assertIn("Ana\_B", text)

    async def test_a_failing_announcement_does_not_propagate(self):
        send = mock.AsyncMock(side_effect=RuntimeError("down"))
        await self.announce(types.SimpleNamespace(name="Doom", slug="doom"), send)


if __name__ == "__main__":
    unittest.main()

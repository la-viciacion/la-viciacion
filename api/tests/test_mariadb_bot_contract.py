"""The bot against the real API (MariaDB required, see api_support.py).

The bot lives in its own container and reads specific fields of the API's JSON (`game_name`, `played_time`,
`current_streak`...). Its own tests fake the API, so they cannot notice when the API changes shape. Here the
bot's real handlers run with their HTTP calls answered by the API under test, authenticated as the emergency
administrator the bot uses in production: a field renamed on one side fails here, not in the group chat.
"""
import datetime
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import text
from telegram.ext import ApplicationHandlerStop

from tests.api_support import ApiTestCase

# the bot imports its own modules by top-level names, and reads its settings when they are imported
BOT_SRC = Path(__file__).resolve().parents[2] / "bot" / "src"
for name, value in {
    "API_URL": "http://api.test/api/v1", "GOD_ADMIN_PASS": "unused-in-these-tests", "SENTRY_URL_BOT": "", "ENVIRONMENT": "test",
    "BOT_LOG_LEVEL": "INFO", "TELEGRAM_TOKEN": "123456789:" + "A" * 30, "TELEGRAM_GROUP_ID": "-1001234567890",
}.items():
    os.environ.setdefault(name, value)
if str(BOT_SRC) not in sys.path:
    sys.path.append(str(BOT_SRC))

import utils.messages as bot_messages  # noqa: E402  (the bot's own package, not the API's)
from routes.my_routes import MyRoutes  # noqa: E402
from routes.ranking_routes import RankingRoutes  # noqa: E402
from utils.my_utils import ApiError, MyUtils  # noqa: E402
from tests import clock
from tests.clock import ago

GROUP = -1001234567890


def callback_update(sender_id=111):
    query = SimpleNamespace(answer=mock.AsyncMock(), edit_message_text=mock.AsyncMock())
    sender = SimpleNamespace(id=sender_id, is_bot=False, username="ana", first_name="Ana")
    chat = SimpleNamespace(id=sender_id, type="private")
    return SimpleNamespace(effective_chat=chat, effective_user=sender, message=None, callback_query=query)


def message_update(text, sender_id, username, chat_type="private", chat_id=None):
    sender = SimpleNamespace(id=sender_id, is_bot=False, username=username, first_name=username.capitalize())
    chat = SimpleNamespace(id=chat_id if chat_id is not None else sender_id, type=chat_type)
    message = SimpleNamespace(text=text, chat=chat, from_user=sender, reply_text=mock.AsyncMock())
    return SimpleNamespace(effective_chat=chat, effective_user=sender, message=message, callback_query=None)


def context(app_user=None):
    return SimpleNamespace(bot=SimpleNamespace(username="LaViciacionBot"), user_data={"app_user": app_user} if app_user else {})


class BotContractTestCase(ApiTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.god = self.user("admin", admin=True)  # the account the bot logs in as
        self.ana = self.user("ana", telegram_id=111)
        self.bea = self.user("bea", telegram_id=222)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")

        def through_the_api(_self, method, url, json=None):
            path = url.split("/api/v1", 1)[1]
            return self.client.request(method, "/api/v1" + path, headers=self.headers("admin"), json=json)

        patcher = mock.patch.object(MyUtils, "make_request", through_the_api)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def answer(self, handler, username="ana"):
        """Runs a bot handler as `username` and returns the text it sent."""
        update = callback_update()
        app_user = next(u for u in self.api("GET", "/users/", as_user="admin").json() if u["username"] == username)
        await handler(update, context(app_user))
        return update.callback_query.edit_message_text.await_args.args[0]

    def play(self):
        """ana: Celeste 2 h (completed) and Hades 30 min, on three consecutive days; bea: Hades 1 h."""
        today = datetime.date.today()
        self.library_entry(self.ana, "celeste", today, "pc", completed=1, completed_date=today)
        self.library_entry(self.ana, "hades", today, "pc")
        self.library_entry(self.bea, "hades", today, "pc")
        self.session(self.ana, "celeste", ago(days=2, hours=3), 60)
        self.session(self.ana, "celeste", ago(days=1, hours=3), 60)
        self.session(self.ana, "hades", ago(hours=3), 30)
        self.session(self.bea, "hades", ago(hours=5), 60)


class GateAgainstTheApiTests(BotContractTestCase):
    async def gate(self, update):
        ctx = context()
        await MyUtils().gate(update, ctx)
        return ctx

    async def test_an_account_is_found_by_its_telegram_id_with_the_fields_the_bot_uses(self):
        ctx = await self.gate(message_update("/menu", 111, "ana"))
        account = ctx.user_data["app_user"]
        self.assertEqual((account["username"], account["telegram_id"], account["is_active"]), ("ana", 111, 1))
        self.assertIn("name", account)

    async def test_somebody_not_registered_is_refused_with_the_bot_s_own_message(self):
        update = message_update("/menu", 999, "stranger")
        with self.assertRaises(ApplicationHandlerStop):
            await self.gate(update)
        update.message.reply_text.assert_awaited_once_with(bot_messages.forbidden)

    async def test_a_disabled_account_does_not_get_in(self):
        self.user("off", active=False, telegram_id=333)
        update = message_update("/menu", 333, "off")
        with self.assertRaises(ApplicationHandlerStop):
            await self.gate(update)
        update.message.reply_text.assert_awaited_once()  # told that it cannot use the bot

    async def test_the_emergency_account_is_not_a_player_the_bot_can_see(self):
        with self.assertRaises(ApplicationHandlerStop):
            await self.gate(message_update("/menu", 12345, "admin"))  # not even if somebody tried to claim it


class ActivateAgainstTheApiTests(BotContractTestCase):
    async def activate(self, sender_id, username):
        update = message_update("/activate", sender_id, username, chat_type="supergroup", chat_id=GROUP)
        await MyUtils().activate(update, context())
        return update.message.reply_text.await_args.args[0]

    async def test_the_telegram_id_is_stored_on_the_account_with_that_username(self):
        self.user("luis")
        text = await self.activate(777, "luis")
        self.assertEqual(text, bot_messages.activated.format(name="Luis"))
        self.assertEqual(self.scalar("SELECT telegram_id FROM users WHERE username = 'luis'"), 777)

    async def test_it_changes_nothing_else_about_the_account(self):
        luis = self.user("luis", email="luis@example.com")
        before = tuple(self.rows("SELECT name, email, is_admin, is_active FROM users WHERE id = :i", i=luis)[0])
        await self.activate(777, "luis")
        self.assertEqual(tuple(self.rows("SELECT name, email, is_admin, is_active FROM users WHERE id = :i", i=luis)[0]), before)

    async def test_a_linked_account_is_never_overwritten_and_an_already_linked_sender_is_told_so(self):
        taken = await self.activate(555, "ana")  # ana is linked to 111
        self.assertEqual(taken, bot_messages.activate_taken)
        self.assertEqual(self.scalar("SELECT telegram_id FROM users WHERE username = 'ana'"), 111)
        again = await self.activate(111, "ana")
        self.assertEqual(again, bot_messages.already_activated)

    async def test_a_telegram_id_the_api_refuses_reaches_the_error_handler(self):
        self.user("luis")
        with mock.patch.object(MyUtils, "make_request", side_effect=lambda *a, **k: SimpleNamespace(status_code=409, text="conflict", json=lambda: {})):
            with self.assertRaises(ApiError):
                await self.activate(777, "luis")


class StatisticsAgainstTheApiTests(BotContractTestCase):
    async def test_my_games_lists_what_the_user_played_with_its_time(self):
        self.play()
        text = await self.answer(MyRoutes().my_games)
        self.assertTrue(text.startswith("Has jugado a 2 juegos. Estos son los 10 últimos:\n"))
        self.assertIn("(02h00m)", text)
        self.assertIn("Celeste", text)
        self.assertIn("Hades (00h30m)", text)

    async def test_the_top_games_the_completed_ones_and_the_achievements(self):
        self.play()
        top = await self.answer(MyRoutes().my_top_games)
        self.assertEqual(top.splitlines()[:2], ["Este es tu top de juegos:", "1. Celeste - 02h00m"])
        self.assertEqual(await self.answer(MyRoutes().my_completed_games), "Estos son tus últimos juegos completados:\n1. Celeste\n")
        self.assertEqual(await self.answer(MyRoutes().my_achievements), "Estos son tus logros:\n")
        achievement = self.scalar("SELECT id FROM achievements ORDER BY id LIMIT 1")
        title = self.scalar("SELECT title FROM achievements WHERE id = :a", a=achievement)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) VALUES (:u, :a, CURDATE())"), {"u": self.ana, "a": achievement})
        self.assertEqual(await self.answer(MyRoutes().my_achievements), f"Estos son tus logros:\n1. {title}\n")

    async def test_the_streak_reads_the_three_fields_the_api_gives(self):
        self.play()
        text = await self.answer(MyRoutes().my_streak)
        self.assertTrue(text.startswith("Estos son tus rachas:\nRacha actual: 3\nMejor racha: 3\nFin mejor racha: "))

    async def test_recommendations_are_the_games_others_have_and_the_user_never_had(self):
        self.game("tetris", "Tetris")
        today = datetime.date.today()
        self.library_entry(self.ana, "celeste", today, "pc")
        for user in (self.bea, self.god):
            self.library_entry(user, "tetris", today, "pc")
        text = await self.answer(MyRoutes().recommendations)
        self.assertEqual(text, "Juegos que tienen los demás y tú no has jugado:\n1. Tetris (Bea)\n")

    async def test_a_player_with_nothing_to_be_recommended_gets_the_friendly_answer(self):
        self.assertIn("No hay nada que recomendarte", await self.answer(MyRoutes().recommendations))


class RankingsAgainstTheApiTests(BotContractTestCase):
    async def test_every_ranking_handler_works_against_the_real_api_and_prints_the_players(self):
        self.play()
        routes = RankingRoutes()
        handlers = [routes.user_hours, routes.user_days, routes.user_played_games, routes.user_achievements, routes.user_best_streak,
                    routes.user_current_streak, routes.user_ratio, routes.user_completed_games, routes.games_most_played]
        for handler in handlers:
            with self.subTest(handler=handler.__name__):
                text = await self.answer(handler)
                self.assertGreater(len(text.splitlines()), 0 if handler.__name__ == "user_achievements" else 1)  # no achievements yet
                self.assertNotIn("Traceback", text)

    async def test_the_hours_ranking_orders_the_players_with_their_durations(self):
        self.play()
        text = await self.answer(RankingRoutes().user_hours)
        self.assertEqual(text.splitlines()[:3], ["Así está el ranking de horas de vicio:", "1. Ana: 02h30m", "2. Bea: 01h00m"])

    async def test_the_other_rankings_print_their_values(self):
        self.play()
        routes = RankingRoutes()
        self.assertEqual((await self.answer(routes.user_days)).splitlines()[1:3], ["1. Ana: 3", "2. Bea: 1"])
        self.assertEqual((await self.answer(routes.user_completed_games)).splitlines()[1], "1. Ana: 1")
        self.assertEqual((await self.answer(routes.user_current_streak)).splitlines()[1], "1. Ana: 3")
        self.assertEqual((await self.answer(routes.games_most_played)).splitlines()[1:3], ["1. Celeste: 02h00m", "2. Hades: 01h30m"])

    async def test_the_fields_each_handler_reads_exist_in_the_api_answer(self):
        """The contract, spelled out: ranking key -> the fields the bot prints."""
        self.play()
        reads = {
            "user_hours": ("name", "played_time"), "user_days": ("name", "played_days"), "user_played_games": ("name", "played_games"),
            "achievements": ("name", "achievements"), "user_best_streak": ("name", "best_streak"),
            "user_current_streak": ("name", "current_streak"), "user_ratio": ("name", "ratio"),
            "user_completed_games": ("name", "completed_games"), "games_most_played": ("name", "played_time"),
        }
        for key, fields in reads.items():
            with self.subTest(ranking=key):
                rows = self.api("GET", "/statistics/rankings", as_user="admin", params={"ranking": key}).json()[0]["data"]
                for row in rows:
                    for field in fields:
                        self.assertIn(field, row)
        for key, fields in {"played_games": ("game_name", "played_time"), "top_games": ("game_name", "played_time"),
                            "completed_games": ("game_name",), "achievements": ("title",)}.items():
            with self.subTest(statistic=key):
                rows = self.api("GET", "/statistics/users/ana", as_user="admin", params={"ranking": key}).json()[0]["data"]
                for row in rows:
                    for field in fields:
                        self.assertIn(field, row)
        streak = self.api("GET", "/statistics/users/ana", as_user="admin", params={"ranking": "streak"}).json()[0]["data"]
        self.assertTrue({"current_streak", "best_streak", "best_streak_date"} <= set(streak))

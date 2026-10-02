"""What the bot answers: the text of every statistic and ranking, the menus, and that the keyboards and the
handlers of app.py agree (a button with no handler behind it would do nothing)."""
import re
import unittest
from unittest import mock

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)
from tests.support import make_context, make_update, user

from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, TypeHandler

import app as bot_app
import utils.keyboard as kb
from routes.basic_routes import BasicRoutes
from routes.my_routes import MyRoutes
from routes.ranking_routes import RankingRoutes
from utils.my_utils import ApiError, MyUtils

utils = MyUtils()
ANA = user(111, "ana", "Ana")


class RouteTestCase(unittest.IsolatedAsyncioTestCase):
    def given(self, api_answer):
        """The API answers `api_answer` to whatever the handler asks; returns the recorder of what was asked."""
        patcher = mock.patch.object(MyUtils, "fetch_json", return_value=api_answer)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    async def run_route(self, handler):
        update = make_update(callback=True)
        result = await handler(update, make_context(ANA))
        update.callback_query.answer.assert_awaited_once_with()
        text = update.callback_query.edit_message_text.await_args.args[0]
        return text, result, update

    def asked(self):
        return self.fetch.call_args.args[1]


class MyStatisticsTests(RouteTestCase):
    async def test_my_games_counts_them_and_lists_ten_at_most_with_their_time(self):
        data = [{"game_name": f"Game {n}", "played_time": 3725 * n} for n in range(1, 13)]
        self.given([{"data": data}])
        text, result, _ = await self.run_route(MyRoutes().my_games)
        lines = text.splitlines()
        self.assertEqual(lines[0], "Has jugado a 12 juegos. Estos son los 10 últimos:")
        self.assertEqual((lines[1], lines[10]), ("1. Game 1 (01h02m)", "10. Game 10 (10h20m)"))
        self.assertEqual(len(lines), 11)  # the eleventh and twelfth are not shown
        self.assertTrue(self.asked().endswith("/statistics/users/ana?ranking=played_games"))

    async def test_the_top_games_and_the_completed_ones(self):
        self.given([{"data": [{"game_name": "Celeste", "played_time": 7200}, {"game_name": "Hades", "played_time": 60}]}])
        text, _, _ = await self.run_route(MyRoutes().my_top_games)
        self.assertEqual(text, "Este es tu top de juegos:\n1. Celeste - 02h00m\n2. Hades - 00h01m\n")
        self.assertTrue(self.asked().endswith("?ranking=top_games"))
        self.given([{"data": [{"game_name": "Celeste"}, {"game_name": "Hades"}]}])
        text, _, _ = await self.run_route(MyRoutes().my_completed_games)
        self.assertEqual(text, "Estos son tus últimos juegos completados:\n1. Celeste\n2. Hades\n")

    async def test_the_achievements_are_listed_by_title(self):
        self.given([{"data": [{"title": "Siete días"}, {"title": "Madrugador"}]}])
        text, _, _ = await self.run_route(MyRoutes().my_achievements)
        self.assertEqual(text, "Estos son tus logros:\n1. Siete días\n2. Madrugador\n")

    async def test_the_streak_shows_the_current_the_best_and_when_it_ended(self):
        self.given([{"data": {"current_streak": 3, "best_streak": 9, "best_streak_date": "2026-03-07"}}])
        text, _, _ = await self.run_route(MyRoutes().my_streak)
        self.assertEqual(text, "Estos son tus rachas:\nRacha actual: 3\nMejor racha: 9\nFin mejor racha: 2026-03-07")

    async def test_an_empty_statistic_is_a_header_without_rows_not_an_error(self):
        self.given([{"data": []}])
        text, _, _ = await self.run_route(MyRoutes().my_achievements)
        self.assertEqual(text, "Estos son tus logros:\n")

    async def test_recommendations_name_the_game_and_who_has_it(self):
        self.given([{"game_name": "Hades", "players": ["Bea"]}, {"game_name": "Tetris", "players": ["Bea", "Cai", "Dan", "Eva"]}])
        text, _, _ = await self.run_route(MyRoutes().recommendations)
        self.assertEqual(text, "Juegos que tienen los demás y tú no has jugado:\n1. Hades (Bea)\n2. Tetris (Bea, Cai, Dan y 1 más)\n")
        self.assertTrue(self.asked().endswith("/users/ana/recommendations?limit=10"))

    async def test_nothing_to_recommend_says_so(self):
        self.given([])
        text, _, _ = await self.run_route(MyRoutes().recommendations)
        self.assertIn("No hay nada que recomendarte", text)

    async def test_an_api_failure_reaches_the_error_handler_instead_of_being_swallowed(self):
        with mock.patch.object(MyUtils, "fetch_json", side_effect=ApiError(500)):
            with self.assertRaises(ApiError):
                await self.run_route(MyRoutes().my_games)


class RankingTextTests(RouteTestCase):
    async def check(self, handler, key, rows, header, expected_rows):
        self.given([{"data": rows}])
        text, result, _ = await self.run_route(handler)
        self.assertTrue(self.asked().endswith(f"/statistics/rankings?ranking={key}"), self.asked())
        self.assertEqual(text, header + expected_rows)

    async def test_every_ranking_asks_for_its_own_key_and_prints_position_name_and_value(self):
        routes = RankingRoutes()
        two = [{"name": "Ana", "{v}": None}, {"name": "Bea", "{v}": None}]
        cases = [
            (routes.user_hours, "user_hours", "played_time", [7200, 60], "Así está el ranking de horas de vicio:\n", "1. Ana: 02h00m\n2. Bea: 00h01m\n"),
            (routes.user_days, "user_days", "played_days", [12, 3], "Así está el ranking de días de vicio:\n", "1. Ana: 12\n2. Bea: 3\n"),
            (routes.user_played_games, "user_played_games", "played_games", [5, 2], "Ranking de juegos jugados:\n", "1. Ana: 5\n2. Bea: 2\n"),
            (routes.user_achievements, "achievements", "achievements", [8, 1], "Ranking de logros:\n", "1. Ana: 8\n2. Bea: 1\n"),
            (routes.user_best_streak, "user_best_streak", "best_streak", [9, 4], "Así va el ranking de racha de días:\n", "1. Ana: 9\n2. Bea: 4\n"),
            (routes.user_current_streak, "user_current_streak", "current_streak", [3, 0], "Estas son las rachas de días actuales:\n", "1. Ana: 3\n2. Bea: 0\n"),
            (routes.user_ratio, "user_ratio", "ratio", [0.5, 0.25], "Así está el ranking de ratio (completados / jugados):\n", "1. Ana: 0.5\n2. Bea: 0.25\n"),
            (routes.user_completed_games, "user_completed_games", "completed_games", [6, 2], "Ranking de juegos completados:\n", "1. Ana: 6\n2. Bea: 2\n"),
        ]
        for handler, key, field, values, header, rows in cases:
            with self.subTest(ranking=key):
                data = [{"name": "Ana", field: values[0]}, {"name": "Bea", field: values[1]}]
                await self.check(handler, key, data, header, rows)

    async def test_the_most_played_games_ranking_names_games_not_players(self):
        await self.check(RankingRoutes().games_most_played, "games_most_played",
                         [{"name": "Celeste", "played_time": 36000}], "Ranking de juegos más jugados:\n", "1. Celeste: 10h00m\n")

    async def test_an_empty_ranking_is_just_the_header(self):
        await self.check(RankingRoutes().user_hours, "user_hours", [], "Así está el ranking de horas de vicio:\n", "")


class MenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_greets_by_name_and_shows_the_main_keyboard(self):
        update = make_update("/menu", first_name="Ana")
        state = await BasicRoutes().menu(update, make_context(ANA))
        text = update.message.reply_text.await_args.args[0]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual((text, state), ("Hola Ana, elije una opción:", utils.MAIN_MENU))
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual([b.callback_data for row in markup.inline_keyboard for b in row], ["my_data", "rankings", "recommendations", "cancel"])

    async def test_back_returns_to_the_main_menu_and_end_closes_the_conversation(self):
        update = make_update(callback=True)
        self.assertEqual(await BasicRoutes().back(update, make_context(ANA)), utils.MAIN_MENU)
        self.assertEqual(update.callback_query.edit_message_text.await_args.kwargs["text"], "Elije una opción:")
        update = make_update(callback=True)
        self.assertEqual(await BasicRoutes().end(update, make_context(ANA)), ConversationHandler.END)
        self.assertEqual(update.callback_query.edit_message_text.await_args.kwargs["text"], "Taluego!")

    async def test_the_submenus_open_with_their_own_keyboards_and_states(self):
        update = make_update(callback=True)
        self.assertEqual(await MyRoutes().my_data(update, make_context(ANA)), utils.MY_ROUTES)
        self.assertEqual(update.callback_query.edit_message_text.await_args.kwargs["text"], "¿Qué quieres consultar?")
        update = make_update(callback=True)
        self.assertEqual(await RankingRoutes().rankings(update, make_context(ANA)), utils.RANKING_ROUTES)
        self.assertEqual(update.callback_query.edit_message_text.await_args.kwargs["text"], "Elije un ranking:")


class WiringTests(unittest.TestCase):
    """Builds the application the way main() does, without polling, and checks what was registered."""

    @classmethod
    def setUpClass(cls):
        cls.handlers = []
        cls.registered = {}

        class Builder:
            def token(self, _):
                return self

            def post_init(self, _):
                return self

            def build(self_inner):
                return cls.FakeApp()

        class FakeApp:
            def add_error_handler(self, handler):
                cls.registered["error_handler"] = handler

            def add_handler(self, handler, group=0):
                cls.handlers.append((handler, group))

            def run_polling(self):
                cls.registered["polled"] = True

        cls.FakeApp = FakeApp
        with mock.patch.object(bot_app, "ApplicationBuilder", return_value=Builder()):
            bot_app.main()
        cls.conversation = next(h for h, _ in cls.handlers if isinstance(h, ConversationHandler))

    def test_the_gate_runs_before_everything_else_and_the_error_handler_is_the_apps(self):
        gate, group = self.handlers[0]
        self.assertIsInstance(gate, TypeHandler)
        self.assertEqual(group, -1)
        self.assertIs(self.registered["error_handler"], bot_app.on_error)
        self.assertTrue(self.registered["polled"])

    def test_the_commands_are_registered_outside_the_conversation(self):
        commands = {tuple(h.commands) for h, _ in self.handlers if isinstance(h, CommandHandler)}
        self.assertEqual(commands, {("activate",), ("start",)})
        entry = self.conversation.entry_points[0]
        self.assertEqual(tuple(entry.commands), ("menu",))

    def test_every_button_of_every_keyboard_has_a_handler_in_the_state_where_it_is_shown(self):
        states = self.conversation.states
        for name, keyboard, state in (("main menu", kb.MAIN_MENU, utils.MAIN_MENU), ("my data", kb.MY_DATA, utils.MY_ROUTES),
                                      ("ranking menu", kb.RANKING_MENU, utils.RANKING_ROUTES)):
            patterns = [h.pattern for h in states[state] if isinstance(h, CallbackQueryHandler)]
            for row in keyboard:
                for button in row:
                    with self.subTest(keyboard=name, button=button.callback_data):
                        self.assertTrue(any(p.match(button.callback_data) for p in patterns), "a button nobody answers")

    def test_every_handler_pattern_belongs_to_a_button_that_exists(self):
        shown = {b.callback_data for keyboard in (kb.MAIN_MENU, kb.MY_DATA, kb.RANKING_MENU) for row in keyboard for b in row}
        for state, handlers in self.conversation.states.items():
            for handler in handlers:
                literal = re.fullmatch(r"\^(\w+)\$", handler.pattern.pattern)
                with self.subTest(state=state, pattern=handler.pattern.pattern):
                    self.assertIsNotNone(literal)
                    self.assertIn(literal.group(1), shown, "a handler no button can trigger")

    def test_the_conversation_is_per_user_and_expires(self):
        self.assertTrue(self.conversation.per_user)
        self.assertEqual(self.conversation.conversation_timeout, 60)


class FakeUpdate:
    """Stands in for telegram.Update, whose attributes are read-only: on_error checks isinstance(update, Update)."""

    def __init__(self, **attributes):
        self.__dict__.update(attributes)


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    def update(self, **kwargs):
        update = FakeUpdate(**vars(make_update(**kwargs)))
        update.effective_message = update.message
        patcher = mock.patch.object(bot_app, "Update", FakeUpdate)
        patcher.start()
        self.addCleanup(patcher.stop)
        return update

    async def test_a_failure_while_answering_a_message_ends_in_a_short_apology(self):
        update = self.update(text="/menu")
        await bot_app.on_error(update, make_context())
        self.assertIn("Inténtalo de nuevo", update.message.reply_text.await_args.args[0])

    async def test_a_failure_in_a_button_edits_the_message(self):
        update = self.update(callback=True)
        await bot_app.on_error(update, make_context())
        update.callback_query.answer.assert_awaited_once_with()
        self.assertIn("Inténtalo de nuevo", update.callback_query.edit_message_text.await_args.args[0])

    async def test_something_that_is_not_an_update_gets_no_reply(self):
        await bot_app.on_error(object(), make_context())  # nothing to answer to; must not raise

    async def test_failing_to_apologise_does_not_raise(self):
        update = self.update(text="/menu")
        update.message.reply_text = mock.AsyncMock(side_effect=RuntimeError("telegram is down"))
        await bot_app.on_error(update, make_context())


class PostInitTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_group_also_lists_activate_but_private_chats_do_not(self):
        application = mock.Mock()
        application.bot.set_my_commands = mock.AsyncMock()
        await bot_app.post_init(application)
        first, second = application.bot.set_my_commands.await_args_list
        self.assertEqual([c.command for c in first.args[0]], ["/start", "/menu"])
        self.assertEqual([c.command for c in second.args[0]], ["/start", "/menu", "/activate"])
        self.assertEqual(second.kwargs["scope"].chat_id, support.GROUP_ID)

    async def test_a_bot_that_is_not_in_the_group_yet_still_starts(self):
        application = mock.Mock()
        application.bot.set_my_commands = mock.AsyncMock(side_effect=[None, RuntimeError("chat not found")])
        await bot_app.post_init(application)
        self.assertEqual(application.bot.set_my_commands.await_count, 2)

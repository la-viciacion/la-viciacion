"""The access gate and /activate: who gets past, what each refusal says, and what /activate writes."""
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)
from tests.support import GROUP_ID, make_context, make_update, user

from telegram.ext import ApplicationHandlerStop

import utils.messages as msgs
from utils.my_utils import ApiError, MyUtils

utils = MyUtils()
USERS = [user(111, "ana", "Ana", user_id=1), user(None, "luis", "Luis", user_id=2), user(333, "off", "Off", is_active=0, user_id=3)]


class GateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        utils.forget_users()
        self.fetch = mock.patch.object(utils, "fetch_json", return_value=USERS)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    async def passes(self, update, context=None):
        context = context or make_context()
        await utils.gate(update, context)
        return context

    async def stops(self, update, context=None):
        context = context or make_context()
        with self.assertRaises(ApplicationHandlerStop):
            await utils.gate(update, context)
        return context

    async def test_a_registered_active_user_in_a_private_chat_gets_in_with_their_account(self):
        context = await self.passes(make_update("/menu"))
        self.assertEqual(context.user_data["app_user"]["username"], "ana")

    async def test_a_registered_user_in_the_app_s_group_may_use_commands(self):
        update = make_update("/menu", chat_type="supergroup", chat_id=GROUP_ID)
        context = await self.passes(update)
        self.assertEqual(context.user_data["app_user"]["username"], "ana")

    async def test_the_account_is_found_by_the_telegram_id_never_by_the_name(self):
        update = make_update("/menu", sender_id=222, username="ana")  # same @username as an account, another id
        await self.stops(update)
        update.message.reply_text.assert_awaited_once_with(msgs.forbidden)

    async def test_an_unregistered_sender_is_told_how_to_proceed(self):
        private = make_update("/menu", sender_id=999)
        await self.stops(private)
        private.message.reply_text.assert_awaited_once_with(msgs.forbidden)
        group = make_update("/menu", chat_type="supergroup", chat_id=GROUP_ID, sender_id=999)
        await self.stops(group)
        group.message.reply_text.assert_awaited_once_with(msgs.forbidden_in_group)

    async def test_a_disabled_account_is_told_so(self):
        update = make_update("/menu", sender_id=333)
        await self.stops(update)
        update.message.reply_text.assert_awaited_once_with(msgs.inactive)

    async def test_other_groups_get_no_answer_at_all(self):
        update = make_update("/menu", chat_type="supergroup", chat_id=-100999)
        await self.stops(update)
        update.message.reply_text.assert_not_awaited()
        self.assertEqual(utils.fetch_json.call_count, 0)

    async def test_channels_and_unknown_chat_types_are_ignored(self):
        for chat_type in ("channel", "sender"):
            await self.stops(make_update("/menu", chat_type=chat_type, chat_id=GROUP_ID))

    async def test_group_chatter_that_is_not_a_command_is_ignored(self):
        update = make_update("anyone up for Hades?", chat_type="supergroup", chat_id=GROUP_ID)
        await self.stops(update)
        update.message.reply_text.assert_not_awaited()

    async def test_a_command_for_another_bot_in_the_group_is_ignored(self):
        await self.stops(make_update("/menu@OtherBot", chat_type="supergroup", chat_id=GROUP_ID))
        await self.passes(make_update("/menu@LaViciacionBot", chat_type="supergroup", chat_id=GROUP_ID))

    async def test_updates_without_a_chat_a_sender_or_a_message_are_dropped(self):
        update = make_update("/menu")
        update.effective_chat = None
        await self.stops(update)
        update = make_update("/menu")
        update.effective_user = None
        await self.stops(update)
        update = make_update("/menu")
        update.message = None  # an edited message, a membership change...
        await self.stops(update)

    async def test_other_bots_are_ignored(self):
        await self.stops(make_update("/menu", is_bot=True))

    async def test_start_and_activate_are_for_people_who_are_not_linked_yet_and_only_in_the_group(self):
        for command in ("/start", "/activate"):
            update = make_update(command, chat_type="supergroup", chat_id=GROUP_ID, sender_id=999)
            context = await self.passes(update)  # no account needed, no API call
            self.assertNotIn("app_user", context.user_data)
        self.assertEqual(utils.fetch_json.call_count, 0)
        await self.stops(make_update("/activate"))  # in private /activate goes nowhere
        await self.passes(make_update("/start", sender_id=111))  # /start in private is for everybody who is registered

    async def test_a_pressed_button_is_answered_and_a_refused_one_just_stops_the_spinner(self):
        update = make_update(callback=True, sender_id=999)
        await self.stops(update)
        update.callback_query.answer.assert_awaited_once_with()

    async def test_when_the_api_cannot_be_asked_the_user_is_told_and_nothing_gets_through(self):
        with mock.patch.object(utils, "fetch_json", side_effect=ApiError(500)):
            update = make_update("/menu")
            await self.stops(update)
        update.message.reply_text.assert_awaited_once_with(msgs.api_error)

    async def test_the_accounts_are_asked_for_once_a_minute_at_most(self):
        await self.passes(make_update("/menu"))
        await self.passes(make_update("/menu"))
        self.assertEqual(utils.fetch_json.await_count, 1)
        utils._users_at -= 61  # a minute later
        await self.passes(make_update("/menu"))
        self.assertEqual(utils.fetch_json.await_count, 2)

    async def test_a_failure_while_refusing_is_swallowed(self):
        update = make_update("/menu", sender_id=999)
        update.message.reply_text.side_effect = RuntimeError("telegram is down")
        await self.stops(update)  # still stops, does not raise the reply's error


class ActivateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        utils.forget_users()

    async def activate(self, users, sender_id=222, username="luis"):
        update = make_update("/activate", chat_type="supergroup", chat_id=GROUP_ID, sender_id=sender_id, username=username)
        calls = []

        def fetch(method, url, json=None):
            calls.append((method, url, json))
            return users

        with mock.patch.object(utils, "fetch_json", side_effect=fetch):
            await utils.activate(update, make_context())
        return update.message.reply_text.await_args.args[0], calls

    async def test_it_links_the_sender_to_the_account_with_their_username(self):
        text, calls = await self.activate(USERS)
        self.assertEqual(text, msgs.activated.format(name="Luis"))
        self.assertEqual(calls[1][0:2], ("PATCH", mock.ANY))
        self.assertTrue(calls[1][1].endswith("/manage/users/2"))
        self.assertEqual(calls[1][2], {"telegram_id": 222})

    async def test_a_new_link_is_let_in_at_once_and_the_accounts_are_read_fresh(self):
        utils._users = [user(None, "luis", "Luis", user_id=2)]  # what the gate remembers: not linked yet
        _, calls = await self.activate(USERS)
        self.assertEqual(calls[0][0], "GET")  # never the remembered list
        self.assertIsNone(utils._users)

    async def test_it_is_the_only_write_and_only_one_field_is_sent(self):
        _, calls = await self.activate(USERS)
        self.assertEqual([c[0] for c in calls], ["GET", "PATCH"])
        self.assertEqual(list(calls[1][2]), ["telegram_id"])

    async def test_the_outcomes_that_write_nothing(self):
        cases = [
            ("already linked", dict(sender_id=111, username="ana"), msgs.already_activated),
            ("no @username", dict(username=None), msgs.activate_no_username),
            ("no such account", dict(username="stranger"), msgs.activate_no_account),
            ("disabled account", dict(sender_id=444, username="off"), msgs.inactive),
        ]
        for name, kwargs, expected in cases:
            with self.subTest(name):
                text, calls = await self.activate(USERS, **kwargs)
                self.assertEqual(text, expected)
                self.assertEqual([c[0] for c in calls], ["GET"])

    async def test_an_account_already_linked_to_somebody_else_is_never_overwritten(self):
        taken = [user(555, "luis", "Luis", user_id=2)]
        text, calls = await self.activate(taken, sender_id=222, username="luis")
        self.assertEqual(text, msgs.activate_taken)
        self.assertEqual([c[0] for c in calls], ["GET"])

    async def test_the_username_is_matched_ignoring_case(self):
        text, _ = await self.activate(USERS, username="LUIS")
        self.assertEqual(text, msgs.activated.format(name="Luis"))

    async def test_an_api_failure_reaches_the_error_handler(self):
        update = make_update("/activate", chat_type="supergroup", chat_id=GROUP_ID)
        with mock.patch.object(utils, "fetch_json", side_effect=ApiError(502)), self.assertRaises(ApiError):
            await utils.activate(update, make_context())

    async def test_start_greets_by_name_and_mentions_activate_only_in_the_group(self):
        private = make_update("/start", first_name="Ana")
        await utils.start(private, make_context())
        self.assertNotIn("/activate", private.message.reply_text.await_args.args[0])
        group = make_update("/start", chat_type="supergroup", chat_id=GROUP_ID, first_name="Ana")
        await utils.start(group, make_context())
        text = group.message.reply_text.await_args.args[0]
        self.assertIn("Hola Ana", text)
        self.assertIn("/activate", text)


def member(first_name="Marta", username="marta_gg", is_bot=False, telegram_id=777):
    return SimpleNamespace(id=telegram_id, first_name=first_name, username=username, is_bot=is_bot)


class WelcomeGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        utils.forget_users()
        self.fetch = mock.patch.object(utils, "fetch_json", return_value=USERS)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    async def test_a_join_in_the_app_s_group_passes_whoever_added_them_and_asks_nothing(self):
        update = make_update(None, chat_type="supergroup", chat_id=GROUP_ID, sender_id=999, new_members=[member()])
        context = make_context()
        await utils.gate(update, context)  # the sender is not linked: still no refusal
        update.message.reply_text.assert_not_awaited()
        self.assertEqual(utils.fetch_json.call_count, 0)

    async def test_a_join_anywhere_else_gets_no_answer(self):
        update = make_update(None, chat_type="supergroup", chat_id=-100999, new_members=[member()])
        with self.assertRaises(ApplicationHandlerStop):
            await utils.gate(update, make_context())

    async def test_chatter_without_new_members_is_still_ignored(self):
        update = make_update("anyone up for Hades?", chat_type="supergroup", chat_id=GROUP_ID)
        with self.assertRaises(ApplicationHandlerStop):
            await utils.gate(update, make_context())


class WelcomeTests(unittest.IsolatedAsyncioTestCase):
    async def welcome(self, members, reply=None, error=None):
        update = make_update(None, chat_type="supergroup", chat_id=GROUP_ID, new_members=members)
        calls = []

        def fetch(method, url, json=None, timeout=None):
            calls.append((method, url, json, timeout))
            if error:
                raise error
            return reply

        with mock.patch.object(utils, "fetch_json", side_effect=fetch):
            await utils.welcome(update, make_context())
        return [c.args[0] for c in update.message.reply_text.await_args_list], calls

    async def test_it_sends_the_text_the_api_got_from_the_ai(self):
        texts, calls = await self.welcome([member()], reply={"message": "Hola Marta, escribe /activate"})
        self.assertEqual(texts, ["Hola Marta, escribe /activate"])
        self.assertEqual(calls[0][0:2], ("POST", mock.ANY))
        self.assertTrue(calls[0][1].endswith("/manage/welcome-message"))
        self.assertEqual(calls[0][2], {"name": "Marta", "username": "marta_gg"})
        self.assertGreater(calls[0][3], 30)  # the API may wait for the AI that long

    async def test_without_an_ai_text_it_sends_the_fixed_welcome_which_says_to_activate(self):
        texts, _ = await self.welcome([member()], reply={"message": None})
        self.assertEqual(texts, [msgs.welcome("Marta", "marta_gg")])
        self.assertIn("/activate", texts[0])

    async def test_when_the_api_fails_the_welcome_still_goes_out(self):
        texts, _ = await self.welcome([member()], error=ApiError(502))
        self.assertEqual(texts, [msgs.welcome("Marta", "marta_gg")])

    async def test_someone_without_a_username_is_told_to_set_one_first(self):
        with_username = msgs.welcome("Marta", "marta_gg")
        without = msgs.welcome("Marta", None)
        self.assertNotIn("@usuario", with_username)
        self.assertIn("@usuario", without)
        self.assertLess(without.index("@usuario"), without.index("/activate"))

    async def test_bots_are_not_welcomed_and_each_person_gets_their_own_welcome(self):
        texts, calls = await self.welcome(
            [member("Marta"), member("Otro bot", is_bot=True), member("Pepe", username=None, telegram_id=888)],
            reply={"message": None},
        )
        self.assertEqual(texts, [msgs.welcome("Marta", "marta_gg"), msgs.welcome("Pepe", None)])
        self.assertEqual([c[2]["name"] for c in calls], ["Marta", "Pepe"])

    async def test_a_long_or_empty_name_is_cut_to_what_the_api_accepts(self):
        _, calls = await self.welcome([member("x" * 100), member("  ")], reply={"message": None})
        self.assertEqual([len(c[2]["name"]) for c in calls], [64, len("jugador")])

    async def test_a_welcome_is_not_a_write(self):
        _, calls = await self.welcome([member()], reply={"message": None})
        self.assertEqual({c[0] for c in calls}, {"POST"})
        self.assertEqual({c[1].rsplit("/", 1)[1] for c in calls}, {"welcome-message"})


class FetchJsonTests(unittest.IsolatedAsyncioTestCase):
    def response(self, status=200, payload=None, text="body", json_error=False):
        response = mock.Mock(status_code=status, text=text)
        if json_error:
            response.json.side_effect = ValueError("not json")
        else:
            response.json.return_value = payload
        return response

    async def test_a_200_with_json_is_returned_parsed(self):
        with mock.patch.object(utils, "make_request", return_value=self.response(payload=[{"a": 1}])) as request:
            self.assertEqual(await utils.fetch_json("GET", "http://api/x", json={"k": 1}), [{"a": 1}])
        request.assert_called_once_with("GET", "http://api/x", json={"k": 1})

    async def test_any_other_status_is_an_api_error_carrying_the_status(self):
        for status in (401, 404, 500, 502):
            with self.subTest(status=status), mock.patch.object(utils, "make_request", return_value=self.response(status=status)):
                with self.assertRaises(ApiError) as caught:
                    await utils.fetch_json("GET", "http://api/x")
                self.assertEqual(caught.exception.status_code, status)

    async def test_a_body_that_is_not_json_is_an_api_error_too(self):
        with mock.patch.object(utils, "make_request", return_value=self.response(json_error=True)):
            with self.assertRaises(ApiError):
                await utils.fetch_json("GET", "http://api/x")

    async def test_a_slower_request_can_be_given_its_own_timeout(self):
        with mock.patch.object(utils, "make_request", return_value=self.response(payload={})) as request:
            await utils.fetch_json("POST", "http://api/x", json={}, timeout=40)
        request.assert_called_once_with("POST", "http://api/x", json={}, timeout=40)

    async def test_the_request_does_not_block_the_event_loop(self):
        seen = []
        with mock.patch.object(utils, "make_request", side_effect=lambda *a, **k: seen.append(threading.current_thread()) or self.response(payload=[])):
            await utils.fetch_json("GET", "http://api/x")
        self.assertIsNot(seen[0], threading.main_thread())

    def test_the_conversation_states_are_distinct(self):
        self.assertEqual(len({utils.MAIN_MENU, utils.MY_ROUTES, utils.RANKING_ROUTES}), 3)

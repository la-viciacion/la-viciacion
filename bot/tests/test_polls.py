"""The answers to the group's polls: what the bot reports to the API, and that nothing else can use that way in."""
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)
from tests.support import GROUP_ID, make_context

from telegram.ext import ApplicationHandlerStop

from utils.my_utils import utils


def answer(poll_id="555", user_id=111, option_ids=(1,), is_bot=False, voter=True, keys=("k1",)):
    sender = SimpleNamespace(id=user_id, is_bot=is_bot) if voter else None
    return SimpleNamespace(poll_answer=SimpleNamespace(poll_id=poll_id, user=sender, option_ids=list(option_ids), option_persistent_ids=list(keys)), effective_chat=None, effective_user=sender, message=None, callback_query=None)


class PollAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_choice_is_reported_to_the_api_as_it_is(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock(return_value={"recorded": True})) as fetch:
            await utils.poll_answer(answer(option_ids=(0, 2)), make_context())
        method, url = fetch.await_args.args[:2]
        self.assertEqual((method, url.rsplit("/api/v1", 1)[-1]), ("PUT", "/manage/polls/answers"))
        self.assertEqual(fetch.await_args.kwargs["json"], {"poll_id": "555", "user_id": 111, "option_ids": [0, 2], "option_keys": ["k1"]})

    async def test_taking_the_vote_back_is_an_empty_choice(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock()) as fetch:
            await utils.poll_answer(answer(option_ids=()), make_context())
        self.assertEqual(fetch.await_args.kwargs["json"]["option_ids"], [])

    async def test_a_vote_from_a_chat_or_a_bot_is_not_a_person_and_reports_nothing(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock()) as fetch:
            await utils.poll_answer(answer(voter=False), make_context())
            await utils.poll_answer(answer(is_bot=True), make_context())
        fetch.assert_not_awaited()

    async def test_an_api_that_fails_costs_the_vote_but_not_the_bot(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock(side_effect=RuntimeError("down"))):
            await utils.poll_answer(answer(), make_context())  # logged, not raised

    async def test_the_gate_stops_an_answer_so_only_its_own_handler_takes_it(self):
        # it has no chat: the handler is registered before the gate (app.py), and nothing after the gate may see it
        with self.assertRaises(ApplicationHandlerStop):
            await utils.gate(answer(), make_context())


def added(chat_id=GROUP_ID, chat_type="supergroup", poll_message_id=71):
    poll_message = SimpleNamespace(message_id=poll_message_id) if poll_message_id else None
    message = SimpleNamespace(chat=SimpleNamespace(id=chat_id, type=chat_type), poll_option_added=SimpleNamespace(option_persistent_id="k9", option_text="Hollow Knight", poll_message=poll_message))
    return SimpleNamespace(message=message)


class PollOptionAddedTests(unittest.IsolatedAsyncioTestCase):
    async def test_an_option_added_in_the_group_is_reported_to_the_api(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock(return_value={"recorded": True})) as fetch:
            await utils.poll_option_added(added(), make_context())
        method, url = fetch.await_args.args[:2]
        self.assertEqual((method, url.rsplit("/api/v1", 1)[-1]), ("PUT", "/manage/polls/options"))
        self.assertEqual(fetch.await_args.kwargs["json"], {"message_id": 71, "key": "k9", "text": "Hollow Knight"})

    async def test_the_poll_may_be_unknown(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock()) as fetch:
            await utils.poll_option_added(added(poll_message_id=None), make_context())
        self.assertIsNone(fetch.await_args.kwargs["json"]["message_id"])

    async def test_only_the_apps_group_is_listened_to(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock()) as fetch:
            await utils.poll_option_added(added(chat_id=GROUP_ID + 1), make_context())
            await utils.poll_option_added(added(chat_id=5, chat_type="private"), make_context())
        fetch.assert_not_awaited()

    async def test_an_api_that_fails_costs_the_option_but_not_the_bot(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock(side_effect=RuntimeError("down"))):
            await utils.poll_option_added(added(), make_context())  # logged, not raised

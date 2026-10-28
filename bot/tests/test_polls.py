"""The answers to the group's polls: what the bot reports to the API, and that nothing else can use that way in."""
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import support  # noqa: F401  (sets the environment and the path before the bot is imported)
from tests.support import make_context

from telegram.ext import ApplicationHandlerStop

from utils.my_utils import utils


def answer(poll_id="555", user_id=111, option_ids=(1,), is_bot=False, voter=True):
    sender = SimpleNamespace(id=user_id, is_bot=is_bot) if voter else None
    return SimpleNamespace(poll_answer=SimpleNamespace(poll_id=poll_id, user=sender, option_ids=list(option_ids)), effective_chat=None, effective_user=sender, message=None, callback_query=None)


class PollAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_choice_is_reported_to_the_api_as_it_is(self):
        with mock.patch.object(utils, "fetch_json", new=mock.AsyncMock(return_value={"recorded": True})) as fetch:
            await utils.poll_answer(answer(option_ids=(0, 2)), make_context())
        method, url = fetch.await_args.args[:2]
        self.assertEqual((method, url.rsplit("/api/v1", 1)[-1]), ("PUT", "/manage/polls/answers"))
        self.assertEqual(fetch.await_args.kwargs["json"], {"poll_id": "555", "user_id": 111, "option_ids": [0, 2]})

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

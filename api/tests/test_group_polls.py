"""The polls of the Telegram group that need no Telegram and no MariaDB (crud/group_polls.py, utils/polls.py): what a poll
may ask, how a vote is kept and taken back, the tally and the winner, and how a poll is closed whatever Telegram does."""
import asyncio
import datetime
import json
import unittest
from unittest import mock

from src.crud import group_polls
from src.database import models
from src.utils import polls
from tests.sqlite_db import make_session

NOW = datetime.datetime(2026, 10, 28, 12, 0)


class CleanTests(unittest.TestCase):
    def test_blank_options_are_dropped_and_the_text_trimmed(self):
        self.assertEqual(group_polls.clean("  ¿Cuál?  ", [" Hades ", "", "  ", "Celeste"], None, NOW), ("¿Cuál?", ["Hades", "Celeste"]))

    def test_the_limits_of_telegram_are_kept(self):
        for question, options in (("", ["a", "b"]), ("x" * 301, ["a", "b"]), ("¿?", ["a"]), ("¿?", [str(n) for n in range(11)]), ("¿?", ["a", "x" * 101])):
            with self.assertRaises(group_polls.PollError, msg=(question[:5], len(options))):
                group_polls.clean(question, options, None, NOW)
        group_polls.clean("x" * 300, ["a", "x" * 100] + [str(n) for n in range(8)], None, NOW)  # exactly at the limits

    def test_an_option_cannot_be_repeated_whatever_its_case(self):
        with self.assertRaises(group_polls.PollError):
            group_polls.clean("¿?", ["Hades", " hades "], None, NOW)

    def test_the_deadline_must_be_in_the_next_thirty_days(self):
        group_polls.clean("¿?", ["a", "b"], NOW + datetime.timedelta(minutes=1), NOW)
        group_polls.clean("¿?", ["a", "b"], NOW + datetime.timedelta(days=30), NOW)
        for closes_at in (NOW, NOW - datetime.timedelta(hours=1), NOW + datetime.timedelta(days=30, seconds=1)):
            with self.assertRaises(group_polls.PollError, msg=closes_at):
                group_polls.clean("¿?", ["a", "b"], closes_at, NOW)


class TallyTests(unittest.TestCase):
    def test_every_voter_counts_once_per_option_they_chose(self):
        self.assertEqual(group_polls.tally(3, [[0], [0, 2], [2], [2, 2]]), [2, 0, 3])

    def test_a_position_that_is_not_an_option_counts_for_nothing(self):
        self.assertEqual(group_polls.tally(2, [[5], [-1], [1]]), [0, 1])

    def test_the_winner_is_the_most_voted_and_a_tie_has_several_and_nobody_none(self):
        self.assertEqual(group_polls.winners([1, 3, 2]), [1])
        self.assertEqual(group_polls.winners([2, 0, 2]), [0, 2])
        self.assertEqual(group_polls.winners([0, 0]), [])
        self.assertEqual(group_polls.winners([]), [])


class ResultMessageTests(unittest.TestCase):
    def test_a_winner_a_tie_and_nobody(self):
        self.assertEqual(polls.result_message("¿Cuál?", ["Hades", "Celeste"], [3, 1], [0]), "📊 *Encuesta cerrada*\n¿Cuál?\n🏆 Gana *Hades* con 3 votos.")
        self.assertIn("con 1 voto.", polls.result_message("¿?", ["a", "b"], [1, 0], [0]))
        self.assertEqual(polls.result_message("¿?", ["a", "b", "c"], [2, 2, 0], [0, 1]).splitlines()[-1], "🤝 Empate entre *a* y *b* con 2 votos cada una.")
        self.assertEqual(polls.result_message("¿?", ["a", "b"], [0, 0], []).splitlines()[-1], "Nadie votó.")

    def test_what_markdown_would_read_as_formatting_is_escaped(self):
        self.assertIn("*Dead\\_Cells*", polls.result_message("¿?", ["Dead_Cells", "b"], [1, 0], [0]))


def poll(db, options=("Hades", "Celeste", "Tetris"), multiple=False, closes_at=None, telegram_poll_id="555"):
    return group_polls.create(db, None, "¿Cuál?", list(options), multiple, closes_at, telegram_poll_id, 77)


class VotesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()

    def answer(self, who, chosen, poll_id="555", at=NOW):
        return group_polls.record_answer(self.db, poll_id, who, chosen, at)

    def test_a_vote_is_kept_changed_and_taken_back(self):
        row = poll(self.db)
        self.assertTrue(self.answer(10, [0]))
        self.assertTrue(self.answer(10, [2]))  # the later answer replaces the earlier one
        self.assertEqual(self.db.query(models.GroupPollVote).count(), 1)
        self.assertEqual([o["votes"] for o in group_polls.results(self.db, row)["options"]], [0, 0, 1])
        self.assertTrue(self.answer(10, []))
        self.assertEqual(self.db.query(models.GroupPollVote).count(), 0)
        self.assertTrue(self.answer(10, []))  # taking back what was not there changes nothing

    def test_only_a_poll_that_is_ours_and_open_takes_votes(self):
        row = poll(self.db)
        self.assertFalse(self.answer(10, [0], poll_id="999"))
        group_polls.close(self.db, row, None, NOW)
        self.assertFalse(self.answer(10, [0]))
        self.assertEqual(self.db.query(models.GroupPollVote).count(), 0)

    def test_a_poll_with_one_answer_keeps_only_one_and_positions_outside_the_options_are_dropped(self):
        row = poll(self.db)
        self.answer(10, [2, 0, 9, -1])
        self.assertEqual(json.loads(self.db.get(models.GroupPollVote, (row.id, 10)).option_ids), [0])
        self.answer(11, [9])  # nothing valid is a vote taken back
        self.assertIsNone(self.db.get(models.GroupPollVote, (row.id, 11)))

    def test_a_poll_that_allows_several_keeps_them_all(self):
        row = poll(self.db, multiple=True)
        self.answer(10, [2, 0, 2])
        self.assertEqual(json.loads(self.db.get(models.GroupPollVote, (row.id, 10)).option_ids), [0, 2])

    def test_the_tally_names_who_voted_what_and_those_without_an_account_are_last(self):
        row = poll(self.db)
        self.db.add_all([models.User(username="ana", name="Ana", password="x", telegram_id=10), models.User(username="bea", name=None, password="x", telegram_id=11)])
        self.db.commit()
        for who, chosen in ((12, [0]), (10, [0]), (11, [0]), (13, [1])):
            self.answer(who, chosen)
        shown = group_polls.results(self.db, row)
        self.assertEqual([(o["text"], o["votes"]) for o in shown["options"]], [("Hades", 3), ("Celeste", 1), ("Tetris", 0)])
        self.assertEqual([v["name"] for v in shown["options"][0]["voters"]], ["Ana", "bea", None])
        self.assertEqual((shown["winners"], shown["voters"]), ([0], 4))


class ClosingTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.row = poll(self.db)

    def close(self, stop=(True, 3), announce=True, at=NOW):
        with mock.patch.object(polls, "stop", new=mock.AsyncMock(return_value=stop)) as stopping, \
                mock.patch.object(polls.my_utils, "send_message", new=mock.AsyncMock()) as sending:
            newly = asyncio.run(polls.close(self.db, self.row, 5, announce, at))
        return newly, stopping, sending

    def test_closing_ends_it_here_stops_it_in_telegram_and_tells_the_group_the_winner(self):
        group_polls.record_answer(self.db, "555", 10, [1], NOW)
        newly, stopping, sending = self.close()
        self.assertTrue(newly)
        self.assertEqual((self.row.closed_at, self.row.closed_by, self.row.telegram_stopped, self.row.telegram_voters), (NOW, 5, True, 3))
        stopping.assert_awaited_once()
        self.assertIn("Gana *Celeste* con 1 voto", sending.await_args.args[0])
        self.assertIs(sending.await_args.args[1], False)

    def test_a_telegram_that_fails_does_not_keep_the_poll_open_and_is_tried_again(self):
        newly, _, sending = self.close(stop=(False, None))
        self.assertTrue(newly)
        self.assertIsNotNone(self.row.closed_at)
        self.assertFalse(self.row.telegram_stopped)
        sending.assert_awaited_once()  # the winner is told all the same
        self.assertEqual(group_polls.to_stop(self.db, NOW + datetime.timedelta(minutes=5)), [self.row])
        again, _, sending = self.close(stop=(True, 0), at=NOW + datetime.timedelta(minutes=5))
        self.assertFalse(again)  # already closed: nothing is announced twice
        sending.assert_not_awaited()
        self.assertTrue(self.row.telegram_stopped)
        self.assertEqual(self.row.closed_at, NOW)
        self.assertEqual(group_polls.to_stop(self.db, NOW + datetime.timedelta(minutes=6)), [])

    def test_the_retry_gives_up_after_a_day(self):
        self.close(stop=(False, None))
        self.assertEqual(group_polls.to_stop(self.db, NOW + datetime.timedelta(hours=23)), [self.row])
        self.assertEqual(group_polls.to_stop(self.db, NOW + datetime.timedelta(days=1, minutes=1)), [])

    def test_the_winner_is_only_told_when_asked(self):
        _, _, sending = self.close(announce=False)
        sending.assert_not_awaited()

    def test_the_polls_to_close_are_the_open_ones_past_their_deadline(self):
        late = poll(self.db, closes_at=NOW - datetime.timedelta(minutes=1), telegram_poll_id="late")
        poll(self.db, closes_at=NOW + datetime.timedelta(hours=1), telegram_poll_id="future")
        done = poll(self.db, closes_at=NOW - datetime.timedelta(hours=1), telegram_poll_id="done")
        group_polls.close(self.db, done, None, NOW)
        self.assertEqual(group_polls.due(self.db, NOW), [late])  # the one without a deadline is never due
        with mock.patch.object(polls, "stop", new=mock.AsyncMock(return_value=(True, 0))), mock.patch.object(polls.my_utils, "send_message", new=mock.AsyncMock()) as sending:
            self.assertEqual(asyncio.run(polls.close_due(self.db, NOW)), "1 closed")
        self.assertEqual((late.closed_by, late.closed_at), (None, NOW))
        sending.assert_awaited_once()
        self.assertEqual(group_polls.due(self.db, NOW), [])

    def test_answers_missed_are_noticed_when_telegram_counted_more_people(self):
        group_polls.record_answer(self.db, "555", 10, [0], NOW)
        self.close(stop=(True, 3))
        self.assertTrue(group_polls.view(self.db, self.row)["missed_votes"])
        self.row.telegram_voters = 1
        self.assertFalse(group_polls.view(self.db, self.row)["missed_votes"])


class TelegramSendTests(unittest.TestCase):
    """The poll is sent non-anonymous (without it the bot would never hear who voted what)."""

    def send(self, error=None, settings=None):
        bot = mock.MagicMock()
        bot.__aenter__ = mock.AsyncMock(return_value=bot)
        bot.__aexit__ = mock.AsyncMock(return_value=False)
        bot.send_poll = mock.AsyncMock(return_value=mock.Mock(poll=mock.Mock(id="555"), message_id=77), side_effect=error)
        values = {"telegram.token": "t", "telegram.group_id": "-1", **(settings or {})}
        with mock.patch.object(polls.settings, "get", side_effect=lambda key: values[key]), mock.patch.object(polls.telegram, "Bot", return_value=bot):
            try:
                return asyncio.run(polls.send("¿Cuál?", ["Hades", "Celeste"], True)), bot
            except polls.TelegramFailure as e:
                return e, bot

    def test_it_is_not_anonymous_and_gives_back_the_ids_that_answers_and_the_stop_need(self):
        sent, bot = self.send()
        self.assertEqual(sent, ("555", 77))
        self.assertEqual(
            bot.send_poll.await_args.kwargs,
            {"chat_id": "-1", "question": "¿Cuál?", "options": ["Hades", "Celeste"], "is_anonymous": False, "allows_multiple_answers": True},
        )

    def test_a_refusal_of_telegram_is_told_to_the_admin(self):
        failure, _ = self.send(error=polls.telegram.error.BadRequest("Chat not found"))
        self.assertIsInstance(failure, polls.TelegramFailure)
        self.assertIn("Chat not found", str(failure))

    def test_without_the_token_or_the_group_nothing_is_sent(self):
        for missing in ("telegram.token", "telegram.group_id"):
            failure, bot = self.send(settings={missing: None})
            self.assertEqual(str(failure), "Falta el token del bot o el ID del grupo")
            bot.send_poll.assert_not_awaited()


class TelegramStopTests(unittest.TestCase):
    """What `stop` makes of Telegram's answers (the bot is replaced by a stand-in)."""

    def stop(self, result=None, error=None):
        bot = mock.MagicMock()
        bot.__aenter__ = mock.AsyncMock(return_value=bot)
        bot.__aexit__ = mock.AsyncMock(return_value=False)
        bot.stop_poll = mock.AsyncMock(return_value=result, side_effect=error)
        with mock.patch.object(polls.settings, "get", side_effect=lambda key: {"telegram.token": "t", "telegram.group_id": "-1"}[key]), \
                mock.patch.object(polls.telegram, "Bot", return_value=bot):
            return asyncio.run(polls.stop(models.GroupPoll(id=1, telegram_message_id=77)))

    def test_a_poll_stopped_reports_its_voters(self):
        self.assertEqual(self.stop(result=mock.Mock(total_voter_count=4)), (True, 4))

    def test_a_poll_telegram_already_stopped_counts_as_stopped(self):
        error = polls.telegram.error.BadRequest("Poll has already been closed")
        self.assertEqual(self.stop(error=error), (True, None))

    def test_any_other_failure_is_not_stopped_and_never_raises(self):
        self.assertEqual(self.stop(error=polls.telegram.error.BadRequest("message to stop poll not found")), (False, None))
        self.assertEqual(self.stop(error=polls.telegram.error.NetworkError("down")), (False, None))

    def test_without_the_token_it_is_not_stopped(self):
        with mock.patch.object(polls.settings, "get", return_value=None):
            self.assertEqual(asyncio.run(polls.stop(models.GroupPoll(id=1, telegram_message_id=77))), (False, None))


if __name__ == "__main__":
    unittest.main()

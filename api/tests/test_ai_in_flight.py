"""One question at a time for a player whose question the group's key pays, and one row a minute for a stopped player who keeps asking."""
import datetime
import threading
import unittest

from fastapi import HTTPException

from src.database import models
from src.utils import ai_ledger, in_flight, messages
from tests.sqlite_db import make_session
from tests.test_chat import seed


class OneAtATimeTests(unittest.TestCase):
    def tearDown(self):
        in_flight._running.clear()

    def test_a_second_question_while_the_first_runs_is_refused_with_a_wait_message(self):
        with in_flight.one_at_a_time(1, own_key=False):
            with self.assertRaises(HTTPException) as caught:
                with in_flight.one_at_a_time(1, own_key=False):
                    self.fail("it must not run")
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (429, messages.AI_BUSY))

    def test_the_place_is_given_back_when_the_question_ends_even_if_it_fails(self):
        with self.assertRaises(RuntimeError):
            with in_flight.one_at_a_time(1, own_key=False):
                raise RuntimeError("the provider failed")
        with in_flight.one_at_a_time(1, own_key=False):
            pass  # free again

    def test_other_players_and_a_players_own_key_are_not_held(self):
        with in_flight.one_at_a_time(1, own_key=False):
            with in_flight.one_at_a_time(2, own_key=False):
                pass
            with in_flight.one_at_a_time(1, own_key=True):
                pass

    def test_of_many_questions_at_once_only_one_runs(self):
        ran, refused, gate = [], [], threading.Event()
        started = threading.Barrier(5)

        def ask():
            started.wait()
            try:
                with in_flight.one_at_a_time(1, own_key=False):
                    ran.append(1)
                    gate.wait(0.3)
            except HTTPException:
                refused.append(1)

        threads = [threading.Thread(target=ask) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual((len(ran), len(refused)), (1, 4))


class BlockedRowsTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed(self.db)

    def rows(self):
        return self.db.query(models.AiUsage).filter(models.AiUsage.status == ai_ledger.BUDGET).all()

    def test_a_stopped_player_who_keeps_asking_leaves_one_row_a_minute(self):
        for _ in range(5):
            ai_ledger.record_blocked(self.db, user_id=1, feature="chat", question="hola", turns=0)
        self.assertEqual(len(self.rows()), 1)

    def test_another_player_or_another_feature_has_its_own_row(self):
        ai_ledger.record_blocked(self.db, user_id=1, feature="chat", question="hola", turns=0)
        ai_ledger.record_blocked(self.db, user_id=2, feature="chat", question="hola", turns=0)
        ai_ledger.record_blocked(self.db, user_id=1, feature="guide", question="hola", turns=0)
        self.assertEqual(len(self.rows()), 3)

    def test_a_minute_later_it_is_written_again(self):
        ai_ledger.record_blocked(self.db, user_id=1, feature="chat", question="hola", turns=0)
        self.db.query(models.AiUsage).update({"created_at": datetime.datetime.now() - datetime.timedelta(minutes=2)})
        self.db.commit()
        ai_ledger.record_blocked(self.db, user_id=1, feature="chat", question="hola", turns=0)
        self.assertEqual(len(self.rows()), 2)

    def test_the_row_says_the_groups_key_was_the_one_stopped(self):
        ai_ledger.record_blocked(self.db, user_id=1, feature="chat", question="hola", turns=0)
        (row,) = self.rows()
        self.assertEqual((row.key_source, row.user_id, row.cost_micros), (ai_ledger.GROUP, 1, None))


if __name__ == "__main__":
    unittest.main()

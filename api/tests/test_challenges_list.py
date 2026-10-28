"""Which finished challenges the challenges page asks for (crud/challenges.py, no database): the running ones always, the finished
ones only the latest few of each block, so opening the page does not work out the progress of every challenge there ever was."""
import datetime
import json
import types
import unittest

from src.crud import challenges as crud
from src.utils.challenges import DUEL, GROUP, USER

TODAY = datetime.date(2026, 10, 28)
ME, OTHER, THIRD = 1, 2, 3


def challenge(id_, scope, ends_in_days, owner=None, opponent=None):
    return types.SimpleNamespace(
        id=id_, scope=scope, owner_user_id=owner, ends_on=TODAY + datetime.timedelta(days=ends_in_days),
        params=json.dumps({"opponent_id": opponent} if opponent else {}),
    )


def ids(rows):
    return [c.id for c in rows]


class BlockTests(unittest.TestCase):
    def test_each_challenge_belongs_to_the_block_the_page_lists_it_in(self):
        self.assertEqual(crud.block_of(challenge(1, GROUP, -1), ME), "group")
        self.assertEqual(crud.block_of(challenge(2, USER, -1, owner=ME), ME), "mine")
        self.assertEqual(crud.block_of(challenge(3, USER, -1, owner=OTHER), ME), "others")
        self.assertEqual(crud.block_of(challenge(4, DUEL, -1, owner=ME, opponent=OTHER), ME), "duels")
        self.assertEqual(crud.block_of(challenge(5, DUEL, -1, owner=OTHER, opponent=ME), ME), "duels")
        self.assertEqual(crud.block_of(challenge(6, DUEL, -1, owner=OTHER, opponent=THIRD), ME), "others")


class LimitFinishedTests(unittest.TestCase):
    def test_the_challenges_that_are_not_over_are_all_kept(self):
        rows = [challenge(i, GROUP, days) for i, days in enumerate((0, 5, 20, 40), start=1)]  # one ends today: still running
        self.assertEqual(ids(crud.limit_finished(rows, ME, TODAY, 0)), [1, 2, 3, 4])

    def test_only_the_latest_finished_of_each_block_are_kept_in_the_same_order(self):
        rows = [challenge(i, GROUP, -i) for i in range(1, 8)] + [challenge(i, USER, -i, owner=ME) for i in range(10, 14)]
        kept = ids(crud.limit_finished(rows, ME, TODAY, 3))
        self.assertEqual(kept, [1, 2, 3, 10, 11, 12])

    def test_a_block_that_has_no_finished_ones_does_not_use_up_another_block(self):
        rows = [challenge(1, GROUP, -1), challenge(2, GROUP, -2), challenge(3, USER, -1, owner=OTHER), challenge(4, DUEL, -1, owner=OTHER, opponent=THIRD)]
        self.assertEqual(ids(crud.limit_finished(rows, ME, TODAY, 1)), [1, 3])  # the other player's challenges and duels are one block

    def test_without_a_limit_nothing_is_taken_out_and_with_zero_no_finished_one_is_kept(self):
        rows = [challenge(1, GROUP, -1), challenge(2, GROUP, 3)]
        self.assertEqual(ids(crud.limit_finished(rows, ME, TODAY, 0)), [2])


if __name__ == "__main__":
    unittest.main()

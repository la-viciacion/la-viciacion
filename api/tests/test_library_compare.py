"""The pure parts of the game page's pace and of the comparison of two libraries."""
import unittest

from src.crud import game_overview, library_compare


class PaceTests(unittest.TestCase):
    def test_nothing_to_say_when_the_viewer_has_not_played_it(self):
        self.assertIsNone(game_overview.pace(0, False, [3600], 7200))

    def test_the_share_of_the_time_of_the_others_who_completed_it_and_of_the_average(self):
        pace = game_overview.pace(7200, True, [3600, 10800], 14400)
        self.assertEqual(pace, {"seconds": 7200, "completed": True, "group_mean": 7200, "group_count": 2, "group_share": 100, "avg_time": 14400, "avg_share": 50})

    def test_without_the_others_or_the_average_those_comparisons_are_none(self):
        pace = game_overview.pace(5400, False, [], None)
        self.assertEqual((pace["group_mean"], pace["group_count"], pace["group_share"], pace["avg_time"], pace["avg_share"]), (None, 0, None, None, None))
        self.assertEqual(game_overview.pace(5400, False, [], 0)["avg_time"], None)  # 0 is "unknown"

    def test_a_slower_player_is_over_a_hundred(self):
        self.assertEqual(game_overview.pace(9000, True, [6000], 7200)["group_share"], 150)
        self.assertEqual(game_overview.pace(9000, True, [6000], 7200)["avg_share"], 125)


class SplitTests(unittest.TestCase):
    def lib(self, **games):
        return {game: {"seconds": seconds, "completed": False, "score": None} for game, seconds in games.items()}

    def test_shared_only_mine_and_only_theirs_each_most_played_first(self):
        mine = self.lib(a=100, b=900, c=50, d=0)
        theirs = self.lib(a=300, b=10, e=700, f=20)
        shared, only_mine, only_theirs = library_compare.split(mine, theirs)
        self.assertEqual(shared, ["b", "a"])  # 910 against 400
        self.assertEqual(only_mine, ["c", "d"])
        self.assertEqual(only_theirs, ["e", "f"])

    def test_ties_go_by_id_and_empty_libraries_are_fine(self):
        self.assertEqual(library_compare.split(self.lib(b=5, a=5), {}), ([], ["a", "b"], []))
        self.assertEqual(library_compare.split({}, {}), ([], [], []))


if __name__ == "__main__":
    unittest.main()

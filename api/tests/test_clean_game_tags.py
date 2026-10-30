"""The script that passes the tags games already have through the filter (utils/clean_game_tags.py)."""
import unittest

from src.utils import clean_game_tags


class PlanTests(unittest.TestCase):
    ROWS = [("a", "Horror,Steam Cloud,cooperative"), ("b", "Open World,RPG"), ("c", "Steam Achievements"), ("d", "Co-op,CO-OP")]

    def test_only_the_games_that_change_are_listed_with_their_new_tags(self):
        changes, _, _ = clean_game_tags.plan(self.ROWS)
        self.assertEqual(changes, {"a": "Horror", "c": "", "d": "Co-op"})

    def test_it_counts_the_games_that_lose_each_tag_and_the_games_that_have_it(self):
        _, removed, before = clean_game_tags.plan(self.ROWS)
        self.assertEqual(dict(removed), {"Steam Cloud": 1, "cooperative": 1, "Steam Achievements": 1})  # a repeat in another case is not a tag lost
        self.assertEqual(before["RPG"], 1)
        self.assertEqual(len(before), 8)

    def test_running_it_on_its_own_result_changes_nothing(self):
        changes, _, _ = clean_game_tags.plan(self.ROWS)
        again, _, _ = clean_game_tags.plan([(game, changes.get(game, tags)) for game, tags in self.ROWS])
        self.assertEqual(again, {})

    def test_the_report_names_what_goes_most_often_first(self):
        text = clean_game_tags.report(*clean_game_tags.plan(self.ROWS + [("e", "Steam Cloud")]))
        self.assertEqual(text.splitlines()[0], "4 games change; 3 of 8 tags would disappear.")
        self.assertIn("2  Steam Cloud", text.splitlines()[2])


if __name__ == "__main__":
    unittest.main()

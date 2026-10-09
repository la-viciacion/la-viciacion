"""Which games count for the debt and how much of it each leaves (crud/debt._counted_games)."""
import datetime
import unittest

from src.crud import debt

HOUR = 3600
NOW = datetime.datetime(2026, 5, 1, 12, 0)


def counted(sessions, entries, avg=None):
    return debt._counted_games(sessions, entries, {"g": 10 * HOUR} if avg is None else avg)


class CountedGamesTests(unittest.TestCase):
    def test_a_game_in_progress_owes_what_is_left_of_its_average(self):
        self.assertEqual(counted([(1, "g", 4 * HOUR, 2, NOW)], [(1, "g", 0, None)]), {(1, "g"): 6 * HOUR})

    def test_playing_past_the_average_owes_nothing_but_still_counts_as_a_game(self):
        self.assertEqual(counted([(1, "g", 12 * HOUR, 5, NOW)], [(1, "g", 0, None)]), {(1, "g"): 0})

    def test_without_a_session_of_ten_minutes_the_game_does_not_count(self):
        self.assertEqual(counted([(1, "g", 5 * 60, 0, NOW)], [(1, "g", 0, None)]), {})

    def test_without_an_average_time_the_game_does_not_count(self):
        self.assertEqual(counted([(1, "g", HOUR, 1, NOW)], [(1, "g", 0, None)], avg={}), {})
        self.assertEqual(counted([(1, "g", HOUR, 1, NOW)], [(1, "g", 0, None)], avg={"g": 0}), {})

    def test_a_completed_game_does_not_count_even_if_another_platform_is_pending(self):
        entries = [(1, "g", 1, None), (1, "g", 0, None)]
        self.assertEqual(counted([(1, "g", HOUR, 1, NOW)], entries), {})

    def test_an_abandoned_game_does_not_count_until_it_is_played_again(self):
        abandoned_at = NOW - datetime.timedelta(days=3)
        entries = [(1, "g", 0, abandoned_at)]
        self.assertEqual(counted([(1, "g", HOUR, 1, abandoned_at)], entries), {})
        self.assertEqual(counted([(1, "g", HOUR, 1, NOW)], entries), {(1, "g"): 9 * HOUR})

    def test_a_game_abandoned_on_one_platform_still_counts_while_another_is_open(self):
        entries = [(1, "g", 0, NOW - datetime.timedelta(days=3)), (1, "g", 0, None)]
        self.assertEqual(counted([(1, "g", HOUR, 1, NOW - datetime.timedelta(days=5))], entries), {(1, "g"): 9 * HOUR})

    def test_each_player_has_their_own_time(self):
        sessions = [(1, "g", 2 * HOUR, 1, NOW), (2, "g", 9 * HOUR, 3, NOW)]
        entries = [(1, "g", 0, None), (2, "g", 1, None)]
        self.assertEqual(counted(sessions, entries), {(1, "g"): 8 * HOUR})


if __name__ == "__main__":
    unittest.main()

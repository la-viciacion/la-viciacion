import datetime
import unittest

from src.utils import streaks

D = datetime.date
TODAY = D(2026, 9, 30)


def days(start: D, count: int, skip=()):
    return [start + datetime.timedelta(days=i) for i in range(count) if i not in skip]


class StreakSummaryTests(unittest.TestCase):
    def test_no_days_played(self):
        best_date, best, current, _, gap, current_gap = streaks.streak_summary([], TODAY, 2026)
        self.assertEqual((best, current, gap, current_gap), (0, 0, 0, 0))
        self.assertEqual(best_date.year, 2026)

    def test_run_that_reaches_today_is_current(self):
        played = days(TODAY - datetime.timedelta(days=4), 5)  # 5 days ending today
        _, best, current, *_ = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual((best, current), (5, 5))

    def test_run_ending_yesterday_is_still_current(self):
        played = days(TODAY - datetime.timedelta(days=5), 5)  # ends yesterday
        _, best, current, *_ = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual((best, current), (5, 5))

    def test_run_older_than_yesterday_is_not_current(self):
        played = days(TODAY - datetime.timedelta(days=9), 4)  # ends 6 days ago
        _, best, current, _, _, current_gap = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual(current, 0)
        self.assertGreater(best, 0)
        self.assertEqual(current_gap, 5)

    def test_best_streak_is_kept_after_a_break(self):
        long_run = days(D(2026, 3, 1), 10)
        short_run = days(D(2026, 9, 28), 3)
        _, best, current, *_ = streaks.streak_summary(long_run + short_run, TODAY, 2026)
        self.assertEqual(current, 3)
        self.assertEqual(best, 10)


class StreakLengthTests(unittest.TestCase):
    def test_old_run_counts_every_day(self):
        _, best, current, *_ = streaks.streak_summary(days(D(2026, 9, 1), 3), TODAY, 2026)
        self.assertEqual((best, current), (3, 0))

    def test_runs_in_the_middle_count_every_day(self):
        played = days(D(2026, 9, 1), 3) + [D(2026, 9, 10)] + days(D(2026, 9, 29), 2)
        best_date, best, current, *_ = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual((best, current), (3, 2))
        self.assertEqual(best_date, D(2026, 9, 3))

    def test_single_days_are_streaks_of_one(self):
        played = [D(2026, 9, 1), D(2026, 9, 5), D(2026, 9, 9)]
        _, best, current, *_ = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual((best, current), (1, 0))

    def test_single_day_today_is_current(self):
        _, best, current, *_ = streaks.streak_summary([TODAY], TODAY, 2026)
        self.assertEqual((best, current), (1, 1))

    def test_later_run_wins_a_tie(self):
        played = days(D(2026, 9, 1), 3) + days(D(2026, 9, 10), 3)
        best_date, best, *_ = streaks.streak_summary(played, TODAY, 2026)
        self.assertEqual((best, best_date), (3, D(2026, 9, 12)))


class LostStreakTests(unittest.TestCase):
    def test_announced_the_day_the_streak_is_lost(self):
        played = days(D(2026, 9, 10), 15)  # 10..24 September, last played 2026-09-24
        self.assertEqual(streaks.lost_streak(played, D(2026, 9, 26)), 15)

    def test_only_on_that_one_day(self):
        played = days(D(2026, 9, 10), 15)
        for offset in (0, 1):
            self.assertIsNone(streaks.lost_streak(played, D(2026, 9, 24) + datetime.timedelta(days=offset)))
        self.assertIsNone(streaks.lost_streak(played, D(2026, 9, 27)))

    def test_short_streaks_are_not_announced(self):
        played = days(D(2026, 9, 20), 10)  # 20..29 September: 10 days is not more than 10
        self.assertIsNone(streaks.lost_streak(played, D(2026, 10, 1)))

    def test_no_days(self):
        self.assertIsNone(streaks.lost_streak([], TODAY))


if __name__ == "__main__":
    unittest.main()

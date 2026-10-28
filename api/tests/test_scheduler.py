import datetime
import unittest

from src.utils import scheduler

D = datetime.datetime


class SlotTests(unittest.TestCase):
    def test_weekly_slot_is_the_latest_occurrence(self):
        # Wednesday 2026-09-30 10:00, summary on Mondays at 09:00
        self.assertEqual(scheduler.weekly_slot(D(2026, 9, 30, 10, 0), 0, "09:00"), D(2026, 9, 28, 9, 0))

    def test_weekly_slot_before_and_after_the_time_on_the_day(self):
        monday = D(2026, 9, 28)
        self.assertEqual(scheduler.weekly_slot(monday.replace(hour=8, minute=59), 0, "09:00"), D(2026, 9, 21, 9, 0))
        self.assertEqual(scheduler.weekly_slot(monday.replace(hour=9, minute=0, second=1), 0, "09:00"), D(2026, 9, 28, 9, 0))

    def test_weekly_slot_other_weekday(self):
        # Sunday (6) 20:30 seen from Monday morning
        self.assertEqual(scheduler.weekly_slot(D(2026, 9, 28, 7, 0), 6, "20:30"), D(2026, 9, 27, 20, 30))

    def test_monthly_slot_is_the_latest_occurrence(self):
        # the 1st at 10:00, seen from the 18th and from the very morning of the 1st
        self.assertEqual(scheduler.monthly_slot(D(2026, 10, 18, 12, 0), 1, "10:00"), D(2026, 10, 1, 10, 0))
        self.assertEqual(scheduler.monthly_slot(D(2026, 10, 1, 9, 59), 1, "10:00"), D(2026, 9, 1, 10, 0))
        self.assertEqual(scheduler.monthly_slot(D(2026, 10, 1, 10, 0), 1, "10:00"), D(2026, 10, 1, 10, 0))

    def test_monthly_slot_crosses_the_year_and_short_months(self):
        self.assertEqual(scheduler.monthly_slot(D(2027, 1, 1, 9, 0), 1, "10:00"), D(2026, 12, 1, 10, 0))
        self.assertEqual(scheduler.monthly_slot(D(2027, 3, 5, 9, 0), 28, "10:00"), D(2027, 2, 28, 10, 0))

    def test_annual_slot_is_the_latest_occurrence(self):
        # the season's recap on 24 December at 10:00, seen from before and after
        self.assertEqual(scheduler.annual_slot(D(2026, 12, 24, 10, 0), 12, 24, "10:00"), D(2026, 12, 24, 10, 0))
        self.assertEqual(scheduler.annual_slot(D(2026, 12, 24, 9, 59), 12, 24, "10:00"), D(2025, 12, 24, 10, 0))
        self.assertEqual(scheduler.annual_slot(D(2026, 10, 19, 12, 0), 12, 24, "10:00"), D(2025, 12, 24, 10, 0))
        self.assertEqual(scheduler.annual_slot(D(2027, 3, 1, 12, 0), 12, 24, "10:00"), D(2026, 12, 24, 10, 0))

    def test_annual_slot_in_january(self):
        self.assertEqual(scheduler.annual_slot(D(2027, 1, 2, 12, 0), 1, 1, "10:00"), D(2027, 1, 1, 10, 0))
        self.assertEqual(scheduler.annual_slot(D(2026, 10, 19, 12, 0), 1, 1, "10:00"), D(2026, 1, 1, 10, 0))
        self.assertEqual(scheduler.annual_slot(D(2027, 1, 1, 9, 0), 1, 1, "10:00"), D(2026, 1, 1, 10, 0))

    def test_daily_and_hourly_slots(self):
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 4, 59), 5), D(2026, 9, 28, 5, 0))
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 5, 0), 5), D(2026, 9, 29, 5, 0))
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 12, 29), 12, 30), D(2026, 9, 28, 12, 30))
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 12, 30), 12, 30), D(2026, 9, 29, 12, 30))
        self.assertEqual(scheduler.hourly_slot(D(2026, 9, 29, 13, 47, 12)), D(2026, 9, 29, 13, 0))

    def test_minute_slot(self):
        self.assertEqual(scheduler.minute_slot(D(2026, 9, 29, 13, 47, 12, 345)), D(2026, 9, 29, 13, 47))
        self.assertEqual(scheduler.minute_slot(D(2026, 9, 29, 13, 59, 59)), D(2026, 9, 29, 13, 59))

class ForgottenWindowTests(unittest.TestCase):
    def at(self, hour, minute=0):
        return datetime.datetime(2026, 10, 15, hour, minute)

    def test_a_run_covers_the_hour_before_its_slot_when_the_previous_one_ran_in_the_slot_before(self):
        self.assertEqual(scheduler.forgotten_window(self.at(11), self.at(10, 0)), (self.at(10), self.at(11)))
        self.assertEqual(scheduler.forgotten_window(self.at(11), self.at(10, 9)), (self.at(10), self.at(11)))  # a late run: same slot

    def test_the_first_run_ever_covers_the_hour_before(self):
        self.assertEqual(scheduler.forgotten_window(self.at(11), None), (self.at(10), self.at(11)))

    def test_hours_the_scheduler_missed_are_covered_by_the_next_run(self):
        self.assertEqual(scheduler.forgotten_window(self.at(14), self.at(10, 3)), (self.at(10), self.at(14)))

    def test_what_is_made_up_for_is_at_most_a_day(self):
        previous = datetime.datetime(2026, 10, 10, 8, 0)
        self.assertEqual(scheduler.forgotten_window(self.at(14), previous), (self.at(14) - datetime.timedelta(hours=24), self.at(14)))

    def test_consecutive_windows_never_overlap_and_never_leave_a_gap(self):
        runs = [self.at(10, 0), self.at(11, 8), self.at(14, 1), self.at(15, 0)]  # the third after an outage, the second late
        windows = [scheduler.forgotten_window(scheduler.hourly_slot(now), previous) for previous, now in zip(runs, runs[1:])]
        for (_, last), (first, _) in zip(windows, windows[1:]):
            self.assertEqual(last, first)


class DueTests(unittest.TestCase):
    slot = D(2026, 9, 28, 9, 0)
    grace = datetime.timedelta(hours=6)

    def test_due_right_at_the_slot_when_never_run(self):
        self.assertTrue(scheduler.is_due(self.slot, self.slot, None, self.grace))

    def test_not_due_once_it_ran_for_that_slot(self):
        ran = self.slot + datetime.timedelta(seconds=30)
        self.assertFalse(scheduler.is_due(self.slot + datetime.timedelta(minutes=5), self.slot, ran, self.grace))

    def test_due_again_for_the_next_slot(self):
        last_week_run = self.slot - datetime.timedelta(days=7)
        self.assertTrue(scheduler.is_due(self.slot, self.slot, last_week_run, self.grace))

    def test_catches_up_inside_the_grace_window(self):
        # the API was down at 09:00 and is back at 12:00
        self.assertTrue(scheduler.is_due(D(2026, 9, 28, 12, 0), self.slot, None, self.grace))

    def test_skips_a_run_missed_beyond_the_grace_window(self):
        # back on Thursday: this week's summary is skipped
        self.assertFalse(scheduler.is_due(D(2026, 10, 1, 12, 0), self.slot, None, self.grace))

    def test_not_due_before_the_slot_of_the_running_period(self):
        # the latest slot is always in the past, so nothing fires early
        now = D(2026, 9, 28, 8, 59)
        slot = scheduler.weekly_slot(now, 0, "09:00")
        self.assertFalse(scheduler.is_due(now, slot, slot + datetime.timedelta(minutes=1), self.grace))


if __name__ == "__main__":
    unittest.main()

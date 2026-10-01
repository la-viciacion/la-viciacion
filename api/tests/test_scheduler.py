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

    def test_daily_and_hourly_slots(self):
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 4, 59), 5), D(2026, 9, 28, 5, 0))
        self.assertEqual(scheduler.daily_slot(D(2026, 9, 29, 5, 0), 5), D(2026, 9, 29, 5, 0))
        self.assertEqual(scheduler.hourly_slot(D(2026, 9, 29, 13, 47, 12)), D(2026, 9, 29, 13, 0))

    def test_five_minute_slot(self):
        self.assertEqual(scheduler.five_minute_slot(D(2026, 9, 29, 13, 47, 12)), D(2026, 9, 29, 13, 45))
        self.assertEqual(scheduler.five_minute_slot(D(2026, 9, 29, 13, 5, 0)), D(2026, 9, 29, 13, 5))
        self.assertEqual(scheduler.five_minute_slot(D(2026, 9, 29, 13, 59, 59)), D(2026, 9, 29, 13, 55))


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

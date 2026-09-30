import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.utils import user_settings as us


def db_with(row):
    db = MagicMock()
    db.get.return_value = row
    return db


class ForgottenTimerHoursTests(unittest.TestCase):
    def test_without_a_row_the_default_applies(self):
        self.assertEqual(us.forgotten_timer_hours(db_with(None), 1), us.DEFAULT_FORGOTTEN_TIMER_HOURS)

    def test_a_null_column_means_the_default(self):
        row = SimpleNamespace(forgotten_timer_hours=None)
        self.assertEqual(us.forgotten_timer_hours(db_with(row), 1), us.DEFAULT_FORGOTTEN_TIMER_HOURS)

    def test_the_users_value_overrides_the_default(self):
        row = SimpleNamespace(forgotten_timer_hours=8)
        self.assertEqual(us.forgotten_timer_hours(db_with(row), 1), 8)

    def test_get_reports_the_default_next_to_the_value(self):
        self.assertEqual(
            us.get(db_with(None), 1),
            {"forgotten_timer_hours": None, "defaults": {"forgotten_timer_hours": us.DEFAULT_FORGOTTEN_TIMER_HOURS}},
        )


class ValidationTests(unittest.TestCase):
    def test_only_whole_hours_in_range_are_valid(self):
        for ok in (1, 4, 24):
            self.assertTrue(us.valid_forgotten_timer_hours(ok), ok)
        for bad in (0, 25, -1, 2.5, "4", None, True):
            self.assertFalse(us.valid_forgotten_timer_hours(bad), repr(bad))


class UpdateTests(unittest.TestCase):
    def test_creates_the_row_the_first_time(self):
        db = db_with(None)
        us.update(db, 7, {"forgotten_timer_hours": 6})
        added = db.add.call_args.args[0]
        self.assertEqual((added.user_id, added.forgotten_timer_hours), (7, 6))
        db.commit.assert_called_once()

    def test_none_resets_to_the_default_and_absent_keys_are_untouched(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6)
        db = db_with(row)
        us.update(db, 7, {})
        self.assertEqual(row.forgotten_timer_hours, 6)
        us.update(db, 7, {"forgotten_timer_hours": None})
        self.assertIsNone(row.forgotten_timer_hours)


if __name__ == "__main__":
    unittest.main()

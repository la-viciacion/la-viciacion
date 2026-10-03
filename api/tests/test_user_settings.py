import unittest
from types import SimpleNamespace
from unittest import mock
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
            {
                "forgotten_timer_hours": None,
                "timer_notice_minutes": None,
                "show_playing": None,
                "defaults": {
                    "forgotten_timer_hours": us.DEFAULT_FORGOTTEN_TIMER_HOURS,
                    "timer_notice_minutes": us.DEFAULT_TIMER_NOTICE_MINUTES,
                    "show_playing": us.DEFAULT_SHOW_PLAYING,
                },
            },
        )


class ValidationTests(unittest.TestCase):
    def test_only_whole_hours_in_range_are_valid(self):
        for ok in (1, 4, 24):
            self.assertTrue(us.valid_forgotten_timer_hours(ok), ok)
        for bad in (0, 25, -1, 2.5, "4", None, True):
            self.assertFalse(us.valid_forgotten_timer_hours(bad), repr(bad))


class TimerNoticeMinutesTests(unittest.TestCase):
    def test_without_a_row_or_a_value_the_default_applies(self):
        self.assertEqual(us.timer_notice_minutes(db_with(None), 1), us.DEFAULT_TIMER_NOTICE_MINUTES)
        self.assertEqual(us.timer_notice_minutes(db_with(SimpleNamespace(timer_notice_minutes=None)), 1), us.DEFAULT_TIMER_NOTICE_MINUTES)

    def test_the_users_value_overrides_the_default(self):
        self.assertEqual(us.timer_notice_minutes(db_with(SimpleNamespace(timer_notice_minutes=30)), 1), 30)

    def test_it_can_never_be_below_ten_minutes(self):
        self.assertEqual(us.MIN_TIMER_NOTICE_MINUTES, 10)
        for bad in (0, 1, 5, 9, -10):
            self.assertFalse(us.valid_timer_notice_minutes(bad), bad)

    def test_only_whole_minutes_in_range_are_valid(self):
        for ok in (10, 11, 60, 120):
            self.assertTrue(us.valid_timer_notice_minutes(ok), ok)
        for bad in (121, 600, 12.5, "10", None, True):
            self.assertFalse(us.valid_timer_notice_minutes(bad), repr(bad))

    def test_update_sets_and_resets_it_without_touching_the_other_setting(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None)
        db = db_with(row)
        us.update(db, 7, {"timer_notice_minutes": 30})
        self.assertEqual((row.forgotten_timer_hours, row.timer_notice_minutes), (6, 30))
        us.update(db, 7, {"timer_notice_minutes": None})
        self.assertEqual((row.forgotten_timer_hours, row.timer_notice_minutes), (6, None))


class RouteTests(unittest.TestCase):
    """PATCH /users/{username}/settings refuses an interval below the minimum before it reaches the database."""

    def patch(self, **body):
        from fastapi import HTTPException

        from src.database import schemas
        from src.routers import users

        admin = SimpleNamespace(is_admin=True, username="ana", id=1)
        with mock.patch.object(users, "_target_user", return_value=SimpleNamespace(id=1)), mock.patch.object(users.user_settings, "update", return_value={"ok": True}) as update:
            try:
                result = users.update_settings("ana", schemas.UserSettingsUpdate(**body), admin, MagicMock())
            except HTTPException as e:
                return e, update
        return result, update

    def test_below_ten_minutes_is_a_400_and_nothing_is_saved(self):
        for minutes in (1, 5, 9, 0, -5, 121):
            error, update = self.patch(timer_notice_minutes=minutes)
            self.assertEqual(error.status_code, 400, minutes)
            self.assertIn("10", error.detail)
            update.assert_not_called()

    def test_ten_minutes_or_more_is_saved(self):
        result, update = self.patch(timer_notice_minutes=10)
        self.assertEqual(result, {"ok": True})
        update.assert_called_once()
        self.assertEqual(update.call_args.args[2], {"timer_notice_minutes": 10})

    def test_null_resets_to_the_default(self):
        _, update = self.patch(timer_notice_minutes=None)
        self.assertEqual(update.call_args.args[2], {"timer_notice_minutes": None})


class ShowPlayingTests(unittest.TestCase):
    def test_shown_unless_the_user_chose_otherwise(self):
        self.assertTrue(us.show_playing(db_with(None), 1))
        self.assertTrue(us.show_playing(db_with(SimpleNamespace(show_playing=None)), 1))
        self.assertTrue(us.show_playing(db_with(SimpleNamespace(show_playing=True)), 1))
        self.assertFalse(us.show_playing(db_with(SimpleNamespace(show_playing=False)), 1))

    def test_it_is_set_and_reset_without_touching_the_others(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None)
        db = db_with(row)
        us.update(db, 7, {"show_playing": False})
        self.assertEqual((row.forgotten_timer_hours, row.show_playing), (6, False))
        us.update(db, 7, {"show_playing": None})
        self.assertIsNone(row.show_playing)


class UpdateTests(unittest.TestCase):
    def test_creates_the_row_the_first_time(self):
        db = db_with(None)
        us.update(db, 7, {"forgotten_timer_hours": 6})
        added = db.add.call_args.args[0]
        self.assertEqual((added.user_id, added.forgotten_timer_hours), (7, 6))
        db.commit.assert_called_once()

    def test_none_resets_to_the_default_and_absent_keys_are_untouched(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None)
        db = db_with(row)
        us.update(db, 7, {})
        self.assertEqual(row.forgotten_timer_hours, 6)
        us.update(db, 7, {"forgotten_timer_hours": None})
        self.assertIsNone(row.forgotten_timer_hours)


if __name__ == "__main__":
    unittest.main()

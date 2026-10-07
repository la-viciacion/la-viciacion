import datetime
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock

from src.utils import user_settings as us

# the place and the birth date, not set
UNSET = {"place_name": None, "place_latitude": None, "place_longitude": None, "birth_date": None}


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
                "forgotten_timer_telegram": None,
                "forgotten_timer_push": None,
                "place_name": None,
                "place_latitude": None,
                "place_longitude": None,
                "birth_date": None,
                "defaults": {
                    "forgotten_timer_telegram": us.DEFAULT_FORGOTTEN_TIMER_CHANNEL,
                    "forgotten_timer_push": us.DEFAULT_FORGOTTEN_TIMER_CHANNEL,
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


class PlaceAndBirthTests(unittest.TestCase):
    def test_a_place_is_all_three_values_or_none(self):
        full = {"place_name": "Madrid", "place_latitude": 40.4, "place_longitude": -3.7}
        self.assertTrue(us.valid_place({}))  # not asked to change
        self.assertTrue(us.valid_place(full))
        self.assertTrue(us.valid_place({"place_name": None, "place_latitude": None, "place_longitude": None}))
        self.assertFalse(us.valid_place({"place_name": "Madrid"}))
        self.assertFalse(us.valid_place({"place_name": "Madrid", "place_latitude": 40.4, "place_longitude": None}))
        self.assertFalse(us.valid_place({"place_name": None, "place_latitude": 40.4, "place_longitude": -3.7}))

    def test_a_birth_date_is_in_the_past_and_not_before_1900(self):
        today = datetime.date(2027, 6, 1)
        self.assertTrue(us.valid_birth_date(None, today))
        self.assertTrue(us.valid_birth_date(datetime.date(1990, 2, 28), today))
        self.assertTrue(us.valid_birth_date(today, today))
        self.assertFalse(us.valid_birth_date(datetime.date(2027, 6, 2), today))
        self.assertFalse(us.valid_birth_date(datetime.date(1899, 12, 31), today))

    def test_the_place_is_read_as_floats_and_missing_until_chosen(self):
        self.assertIsNone(us.place(db_with(None), 1))
        self.assertIsNone(us.place(db_with(SimpleNamespace(place_latitude=None, place_longitude=None)), 1))
        self.assertEqual(us.place(db_with(SimpleNamespace(place_latitude=Decimal("40.41650"), place_longitude=Decimal("-3.70256"))), 1), (40.4165, -3.70256))
        self.assertIsNone(us.birth_date(db_with(None), 1))

    def test_get_and_update_carry_the_place_and_the_birth_date(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=None, timer_notice_minutes=None, show_playing=None,
                              forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
        db = db_with(row)
        got = us.update(db, 7, {"place_name": "Madrid", "place_latitude": 40.4165, "place_longitude": -3.70256, "birth_date": datetime.date(1990, 6, 15)})
        self.assertEqual((got["place_name"], got["place_latitude"], got["place_longitude"], got["birth_date"]), ("Madrid", 40.4165, -3.70256, "1990-06-15"))
        got = us.update(db, 7, {"place_name": None, "place_latitude": None, "place_longitude": None})
        self.assertEqual((got["place_name"], got["place_latitude"], got["birth_date"]), (None, None, "1990-06-15"))  # the birth date stays


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
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None, forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
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

    def test_an_incomplete_place_or_a_birth_date_in_the_future_is_a_400_and_nothing_is_saved(self):
        for body in ({"place_name": "Madrid"}, {"birth_date": "2999-01-01"}):
            result, update = self.patch(**body)
            self.assertEqual(result.status_code, 400, body)
            update.assert_not_called()
        result, update = self.patch(place_name="Madrid", place_latitude=40.4, place_longitude=-3.7, birth_date="1990-06-15")
        update.assert_called_once()

    def test_a_latitude_out_of_the_globe_is_refused_by_the_schema(self):
        from pydantic import ValidationError

        from src.database import schemas

        with self.assertRaises(ValidationError):
            schemas.UserSettingsUpdate(place_name="x", place_latitude=91, place_longitude=0)

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
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None, forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
        db = db_with(row)
        us.update(db, 7, {"show_playing": False})
        self.assertEqual((row.forgotten_timer_hours, row.show_playing), (6, False))
        us.update(db, 7, {"show_playing": None})
        self.assertIsNone(row.show_playing)


class ForgottenTimerChannelsTests(unittest.TestCase):
    def test_both_channels_are_on_without_a_row_or_a_value(self):
        self.assertEqual(us.forgotten_timer_channels(db_with(None), 1), (True, True))
        row = SimpleNamespace(forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
        self.assertEqual(us.forgotten_timer_channels(db_with(row), 1), (True, True))

    def test_each_channel_follows_the_users_choice(self):
        row = SimpleNamespace(forgotten_timer_telegram=False, forgotten_timer_push=None)
        self.assertEqual(us.forgotten_timer_channels(db_with(row), 1), (False, True))
        row = SimpleNamespace(forgotten_timer_telegram=True, forgotten_timer_push=False)
        self.assertEqual(us.forgotten_timer_channels(db_with(row), 1), (True, False))

    def test_update_sets_and_resets_the_channels_without_touching_the_others(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None,
                              forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
        db = db_with(row)
        us.update(db, 7, {"forgotten_timer_telegram": False, "forgotten_timer_push": False})
        self.assertEqual((row.forgotten_timer_hours, row.forgotten_timer_telegram, row.forgotten_timer_push), (6, False, False))
        us.update(db, 7, {"forgotten_timer_push": None})
        self.assertEqual((row.forgotten_timer_telegram, row.forgotten_timer_push), (False, None))


class UpdateTests(unittest.TestCase):
    def test_creates_the_row_the_first_time(self):
        db = db_with(None)
        us.update(db, 7, {"forgotten_timer_hours": 6})
        added = db.add.call_args.args[0]
        self.assertEqual((added.user_id, added.forgotten_timer_hours), (7, 6))
        db.commit.assert_called_once()

    def test_none_resets_to_the_default_and_absent_keys_are_untouched(self):
        row = SimpleNamespace(user_id=7, forgotten_timer_hours=6, timer_notice_minutes=None, show_playing=None, forgotten_timer_telegram=None, forgotten_timer_push=None, **UNSET)
        db = db_with(row)
        us.update(db, 7, {})
        self.assertEqual(row.forgotten_timer_hours, 6)
        us.update(db, 7, {"forgotten_timer_hours": None})
        self.assertIsNone(row.forgotten_timer_hours)


if __name__ == "__main__":
    unittest.main()

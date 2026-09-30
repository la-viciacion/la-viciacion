import decimal
import unittest

from src.utils import actions
from src.utils import my_utils as utils


class HoursFormatTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(utils.convert_time_to_hours(3600 * 12 + 34 * 60 + 56), "12:34")
        self.assertEqual(utils.convert_time_to_hours(59), "00:00")
        self.assertEqual(utils.convert_time_to_hours(None), "00:00")

    def test_sql_sums_arrive_as_decimal(self):
        self.assertEqual(utils.convert_time_to_hours(decimal.Decimal(5400)), "01:30")


class SignedDifferenceTests(unittest.TestCase):
    def test_sign_and_no_change(self):
        self.assertEqual(actions.signed_difference(3), "+3")
        self.assertEqual(actions.signed_difference(-2), "-2")
        self.assertEqual(actions.signed_difference(0), "=")

    def test_hours_keep_their_sign(self):
        self.assertEqual(actions.signed_difference(-1800, utils.convert_time_to_hours), "-00:30")
        self.assertEqual(actions.signed_difference(5400, utils.convert_time_to_hours), "+01:30")

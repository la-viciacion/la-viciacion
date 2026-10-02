import decimal
import unittest

from src.utils import actions
from src.utils import my_utils as utils


class HoursFormatTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(utils.format_duration(3600 * 12 + 34 * 60 + 56), "12h34m")
        self.assertEqual(utils.format_duration(59), "00h00m")
        self.assertEqual(utils.format_duration(None), "00h00m")

    def test_sql_sums_arrive_as_decimal(self):
        self.assertEqual(utils.format_duration(decimal.Decimal(5400)), "01h30m")


class SignedDifferenceTests(unittest.TestCase):
    def test_sign_and_no_change(self):
        self.assertEqual(actions.signed_difference(3), "+3")
        self.assertEqual(actions.signed_difference(-2), "-2")
        self.assertEqual(actions.signed_difference(0), "=")

    def test_hours_keep_their_sign(self):
        self.assertEqual(actions.signed_difference(-1800, utils.format_duration), "-00h30m")
        self.assertEqual(actions.signed_difference(5400, utils.format_duration), "+01h30m")

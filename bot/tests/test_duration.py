import unittest

from src.utils.duration import format_duration


class FormatDurationTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(format_duration(3725), "01h02m")
        self.assertEqual(format_duration(21 * 3600 + 31 * 60), "21h31m")

    def test_under_an_hour(self):
        self.assertEqual(format_duration(53 * 60), "00h53m")

    def test_none_and_zero(self):
        self.assertEqual(format_duration(None), "00h00m")
        self.assertEqual(format_duration(0), "00h00m")

    def test_more_than_99_hours_keeps_all_digits(self):
        self.assertEqual(format_duration(120 * 3600), "120h00m")


if __name__ == "__main__":
    unittest.main()

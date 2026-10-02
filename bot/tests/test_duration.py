import unittest

from src.utils.duration import format_duration, format_players


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


class FormatPlayersTests(unittest.TestCase):
    def test_lists_up_to_three_names(self):
        self.assertEqual(format_players([]), "")
        self.assertEqual(format_players(["Ana"]), "Ana")
        self.assertEqual(format_players(["Ana", "Bob"]), "Ana y Bob")
        self.assertEqual(format_players(["Ana", "Bob", "Cris"]), "Ana, Bob y Cris")

    def test_counts_the_rest(self):
        self.assertEqual(format_players(["Ana", "Bob", "Cris", "Dan", "Eva"]), "Ana, Bob, Cris y 2 más")


if __name__ == "__main__":
    unittest.main()

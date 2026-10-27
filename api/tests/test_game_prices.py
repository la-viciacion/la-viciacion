"""The pure parts of the prices of the games: the cents, the cost per hour and the group's mean (no database)."""
import unittest

from src.crud import game_prices as gp


class CentsTests(unittest.TestCase):
    def test_euros_become_cents_with_a_comma_or_a_point(self):
        self.assertEqual([gp.cents_of(v) for v in (29.99, "29,99", "29.99", 10, "0", 0.1 + 0.2)], [2999, 2999, 2999, 1000, 0, 30])

    def test_nonsense_and_out_of_range_are_refused(self):
        for bad in ("mucho", "", None, -1, "-0,01", 10001, "abc", float("nan")):
            with self.assertRaises(gp.PriceError, msg=repr(bad)):
                gp.cents_of(bad)
        self.assertEqual(gp.cents_of(10000), gp.MAX_CENTS)  # the limit itself is a price


class PerHourTests(unittest.TestCase):
    def test_cents_per_hour_rounded_and_none_when_too_little_was_played(self):
        self.assertEqual(gp.per_hour(3000, 36000), 300)  # 30 euros over 10 hours
        self.assertEqual(gp.per_hour(1000, 7200), 500)
        self.assertEqual(gp.per_hour(1, 3600), 1)
        self.assertEqual(gp.per_hour(0, 3600), 0)  # a free game costs nothing per hour
        self.assertIsNone(gp.per_hour(3000, gp.MIN_SECONDS - 1))
        self.assertEqual(gp.per_hour(3000, gp.MIN_SECONDS), 6000)


class GroupRowsTests(unittest.TestCase):
    HOUR = 3600

    def test_a_game_needs_three_players_with_a_price_and_time(self):
        prices = {(1, "a"): 3000, (2, "a"): 1500, (3, "a"): 600, (1, "b"): 1000, (2, "b"): 1000}
        seconds = {(1, "a"): 10 * self.HOUR, (2, "a"): 5 * self.HOUR, (3, "a"): self.HOUR, (1, "b"): 4 * self.HOUR, (2, "b"): 4 * self.HOUR}
        rows = gp.group_rows(prices, seconds)
        self.assertEqual(rows, [{"game_id": "a", "contributors": 3, "per_hour_cents": round(5100 / 16)}])  # b has only two: left out

    def test_the_mean_is_the_total_paid_over_the_total_hours_so_who_played_more_weighs_more(self):
        prices = {(1, "a"): 1000, (2, "a"): 1000, (3, "a"): 1000}
        seconds = {(1, "a"): 100 * self.HOUR, (2, "a"): self.HOUR, (3, "a"): self.HOUR}
        self.assertEqual(gp.group_rows(prices, seconds)[0]["per_hour_cents"], round(3000 / 102))

    def test_a_player_who_barely_played_does_not_contribute(self):
        prices = {(1, "a"): 1000, (2, "a"): 1000, (3, "a"): 1000}
        seconds = {(1, "a"): self.HOUR, (2, "a"): self.HOUR, (3, "a"): gp.MIN_SECONDS - 1}
        self.assertEqual(gp.group_rows(prices, seconds), [])  # two contribute: not enough to show it

    def test_the_cheapest_per_hour_first_and_no_player_in_the_answer(self):
        prices = {(u, g): c for g, c in (("cheap", 100), ("dear", 6000)) for u in (1, 2, 3)}
        seconds = {(u, g): self.HOUR for g in ("cheap", "dear") for u in (1, 2, 3)}
        rows = gp.group_rows(prices, seconds)
        self.assertEqual([r["game_id"] for r in rows], ["cheap", "dear"])
        for row in rows:
            self.assertEqual(set(row), {"game_id", "contributors", "per_hour_cents"})  # nobody's id, nobody's price

    def test_nothing_gives_nothing(self):
        self.assertEqual(gp.group_rows({}, {}), [])


if __name__ == "__main__":
    unittest.main()

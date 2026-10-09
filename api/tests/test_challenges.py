"""The templates of the challenges that need no database (utils/challenges.py): periods, numbers, the progress of a
game of the month, the notice texts and what makes two challenges the same."""
import datetime
import json
import types
import unittest

from src.utils import challenges
from src.utils.challenges import Built, ChallengeError


def built(**changes):
    values = dict(title="t", params={"min_hours_each": 5, "min_hours_total": 30}, starts_on=datetime.date(2026, 10, 1),
                  ends_on=datetime.date(2026, 10, 31), game_id="hades")
    return Built(**{**values, **changes})


class PeriodTests(unittest.TestCase):
    def test_a_month_runs_from_its_first_to_its_last_day(self):
        self.assertEqual(challenges.month_period("2026-10"), (datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)))
        self.assertEqual(challenges.month_period("2026-12"), (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31)))
        self.assertEqual(challenges.month_period("2028-02")[1], datetime.date(2028, 2, 29))

    def test_a_month_that_is_not_one_is_refused(self):
        for bad in (None, "", "2026", "2026-13", "x-y", 5):
            with self.assertRaises(ChallengeError, msg=repr(bad)):
                challenges.month_period(bad)

    def test_the_status_follows_the_period(self):
        challenge = types.SimpleNamespace(starts_on=datetime.date(2026, 10, 10), ends_on=datetime.date(2026, 10, 20))
        status = lambda day: challenges.status_of(challenge, datetime.date(2026, 10, day))  # noqa: E731
        self.assertEqual([status(9), status(10), status(20), status(21)], ["upcoming", "active", "active", "finished"])


class HoursTests(unittest.TestCase):
    def test_hours_are_rounded_to_a_tenth_and_kept_within_limits(self):
        self.assertEqual(challenges.hours("2.55", "x"), 2.5)  # round() on a float, banker's rounding is fine
        self.assertEqual(challenges.hours(5, "x"), 5.0)
        for bad in (0, 0.4, -1, challenges.MAX_HOURS + 1, "abc", None):
            with self.assertRaises(ChallengeError, msg=repr(bad)):
                challenges.hours(bad, "Las horas")

    def test_the_texts(self):
        self.assertEqual(challenges.hours_text(5.0), "5")
        self.assertEqual(challenges.hours_text(2.5), "2,5")
        self.assertEqual(challenges.spanish_date(datetime.date(2026, 10, 31)), "31 de octubre")


class FingerprintTests(unittest.TestCase):
    def test_equal_challenges_have_the_same_fingerprint_whatever_the_order_of_the_options(self):
        a = challenges.fingerprint("game_of_month", built(params={"min_hours_each": 5, "min_hours_total": 30}), None)
        b = challenges.fingerprint("game_of_month", built(params={"min_hours_total": 30, "min_hours_each": 5}), None)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_anything_that_differs_changes_it(self):
        base = challenges.fingerprint("game_of_month", built(), None)
        for other in (
            challenges.fingerprint("game_of_month", built(game_id="celeste"), None),
            challenges.fingerprint("game_of_month", built(params={"min_hours_each": 6, "min_hours_total": 30}), None),
            challenges.fingerprint("game_of_month", built(starts_on=datetime.date(2026, 11, 1), ends_on=datetime.date(2026, 11, 30)), None),
            challenges.fingerprint("game_of_month", built(), 7),  # a personal one of somebody
            challenges.fingerprint("themed", built(), None),
        ):
            self.assertNotEqual(base, other)


class GameOfMonthProgressTests(unittest.TestCase):
    NAMES = {1: "Ana", 2: "Bea", 3: "Cai"}

    def test_each_player_has_their_own_part_and_the_group_a_total(self):
        result = challenges.game_of_month_result({1: 7 * 3600, 2: 3 * 3600}, self.NAMES, 5, 30)
        self.assertEqual([(p["name"], p["seconds"], p["done"]) for p in result["players"]], [("Ana", 25200, True), ("Bea", 10800, False), ("Cai", 0, False)])
        self.assertEqual((result["total_seconds"], result["total_target_seconds"], result["total_done"]), (36000, 108000, False))

    def test_the_total_is_reached_whoever_contributes_it(self):
        result = challenges.game_of_month_result({1: 30 * 3600}, self.NAMES, 5, 30)
        self.assertTrue(result["total_done"])
        self.assertEqual([p["done"] for p in result["players"]], [True, False, False])

    def test_a_player_reaches_their_part_exactly_at_the_minimum(self):
        self.assertTrue(challenges.game_of_month_result({1: 5 * 3600}, {1: "Ana"}, 5, 5)["players"][0]["done"])
        self.assertFalse(challenges.game_of_month_result({1: 5 * 3600 - 1}, {1: "Ana"}, 5, 5)["players"][0]["done"])

    def test_nobody_taking_part_never_reaches_the_total(self):
        self.assertFalse(challenges.game_of_month_result({}, {}, 5, 0.5)["total_done"])


class NoticeTests(unittest.TestCase):
    def challenge(self):
        return types.SimpleNamespace(
            params=json.dumps({"min_hours_each": 5, "min_hours_total": 30}), starts_on=datetime.date(2026, 10, 1), ends_on=datetime.date(2026, 10, 31),
        )

    def test_the_launch_says_what_is_asked_and_until_when(self):
        text = challenges.TEMPLATES["game_of_month"].summary(self.challenge())
        self.assertEqual(text, "Mínimo 5 h cada uno y 30 h entre todos, del 1 de octubre al 31 de octubre.")

    def test_the_total_notice_says_how_many_met_their_part(self):
        progress = challenges.game_of_month_result({1: 20 * 3600, 2: 10 * 3600}, {1: "Ana", 2: "Bea", 3: "Cai"}, 5, 30)
        text = challenges.TEMPLATES["game_of_month"].reached(self.challenge(), progress)
        self.assertEqual(text, "Entre todos habéis llegado a las 30 h. 2 de 3 ya habéis cumplido vuestro mínimo.")


if __name__ == "__main__":
    unittest.main()

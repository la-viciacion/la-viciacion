import datetime
import unittest
from unittest import mock

from src.utils import astronomy


def utc(jde):
    """The clock of the tests: UTC, whatever the machine's time zone (the module itself gives local time)."""
    return datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=(jde - astronomy.UNIX_EPOCH_JD) * 86400.0 - astronomy.DELTA_T)


def clear_caches():
    for cached in (astronomy.full_moons, astronomy.eclipses, astronomy.sun_events):
        cached.cache_clear()


class AstronomyTests(unittest.TestCase):
    """The reference moments are the published ones (NASA and the almanacs), in UTC, compared to the minute."""

    @classmethod
    def setUpClass(cls):
        cls.clock = mock.patch.object(astronomy, "_local", utc)
        cls.clock.start()
        clear_caches()

    @classmethod
    def tearDownClass(cls):
        cls.clock.stop()
        clear_caches()

    def assertNear(self, found, expected, minutes=3):
        self.assertLessEqual(abs((found - expected).total_seconds()), minutes * 60, f"{found} vs {expected}")

    def test_a_full_moon_is_found_to_the_minute(self):
        moons = astronomy.full_moons(2026)
        self.assertNear(next(m for m in moons if m.month == 3), datetime.datetime(2026, 3, 3, 11, 38))
        self.assertEqual(len(moons), 13)  # a year has 12 or 13
        self.assertEqual(len(astronomy.full_moons(2027)), 12)

    def test_the_eclipses_of_several_years_are_the_published_ones(self):
        self.assertEqual(
            [(kind, moment.month, moment.day) for kind, moment in astronomy.eclipses(2027)],
            [("solar", 2, 6), ("solar", 8, 2)],  # the lunar ones of 2027 are penumbral: not counted
        )
        self.assertEqual(
            [(kind, moment.month, moment.day) for kind, moment in astronomy.eclipses(2028)],
            [("lunar", 1, 12), ("solar", 1, 26), ("lunar", 7, 6), ("solar", 7, 22), ("lunar", 12, 31)],
        )
        self.assertEqual(
            [(kind, moment.month, moment.day) for kind, moment in astronomy.eclipses(2029)],
            [("solar", 1, 14), ("solar", 6, 12), ("lunar", 6, 26), ("solar", 7, 11), ("solar", 12, 5), ("lunar", 12, 20)],
        )

    def test_the_greatest_eclipse_is_found_to_the_minute(self):
        self.assertNear(astronomy.eclipses(2027)[0][1], datetime.datetime(2027, 2, 6, 15, 59))
        self.assertNear([m for k, m in astronomy.eclipses(2028) if k == "lunar"][-1], datetime.datetime(2028, 12, 31, 16, 52))

    def test_equinoxes_and_solstices_are_found_to_the_minute(self):
        events = astronomy.sun_events(2026)
        self.assertNear(events["SPRING_EQUINOX"], datetime.datetime(2026, 3, 20, 14, 46))
        self.assertNear(events["SUMMER_SOLSTICE"], datetime.datetime(2026, 6, 21, 8, 24))
        self.assertNear(events["AUTUMN_EQUINOX"], datetime.datetime(2026, 9, 23, 0, 5))
        self.assertNear(events["WINTER_SOLSTICE"], datetime.datetime(2026, 12, 21, 20, 50))

    def test_the_days_are_dates_of_the_local_clock(self):
        self.assertIn(datetime.date(2026, 3, 3), astronomy.moon_days(2026))
        self.assertEqual(astronomy.eclipse_days(2028, "lunar"), {datetime.date(2028, 1, 12), datetime.date(2028, 7, 6), datetime.date(2028, 12, 31)})
        self.assertEqual(astronomy.sun_event_days(2027)["WINTER_SOLSTICE"], datetime.date(2027, 12, 22))

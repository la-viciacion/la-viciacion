import datetime
import unittest
from unittest import mock

from src.utils import astronomy


def utc(jde):
    """The clock of the tests: UTC, whatever the machine's time zone (the module itself gives local time)."""
    return datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=(jde - astronomy.UNIX_EPOCH_JD) * 86400.0 - astronomy.DELTA_T)


def clear_caches():
    for cached in (astronomy.full_moons, astronomy._eclipses_of, astronomy._solar_eclipse_days_at, astronomy._lunar_eclipse_nights_at, astronomy.sun_events):
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
        self.assertEqual(astronomy.sun_event_days(2027)["WINTER_SOLSTICE"], datetime.date(2027, 12, 22))


MADRID = (40.4165, -3.7026)
BUENOS_AIRES = (-34.6, -58.4)


class SeenFromACityTests(unittest.TestCase):
    """Which eclipses count for a player: the ones seen from their city, big enough."""

    @classmethod
    def setUpClass(cls):
        cls.clock = mock.patch.object(astronomy, "_local", utc)
        cls.clock.start()
        clear_caches()

    @classmethod
    def tearDownClass(cls):
        cls.clock.stop()
        clear_caches()

    def days(self, year, place=MADRID):
        return sorted(astronomy.solar_eclipse_days_at(year, *place))

    def nights(self, year, place=MADRID):
        return astronomy.lunar_eclipse_nights_at(year, *place)

    def test_the_magnitude_at_a_place_is_the_fraction_of_the_sun_covered_there(self):
        august = [jde for kind, jde, _ in astronomy._eclipses_of(2027) if kind == "solar"][-1]
        magnitude, when = astronomy.solar_eclipse_at(*MADRID, august)
        self.assertAlmostEqual(magnitude, 0.88, delta=0.03)  # total in the south of Spain, partial in Madrid
        self.assertLess(abs(when - august), 0.1)
        self.assertEqual(astronomy.solar_eclipse_at(*BUENOS_AIRES, august)[0], 0.0)  # the Sun is below the horizon there, or far from the path

    def test_a_solar_eclipse_counts_when_it_is_seen_big_enough_from_the_city(self):
        self.assertEqual(self.days(2027), [datetime.date(2027, 8, 2)])
        self.assertEqual(self.days(2029), [])  # four partial eclipses on Earth, none big enough from Madrid
        self.assertEqual(self.days(2034), [])  # the one of March is seen at 0.14: below the minimum
        self.assertEqual(self.days(2027, BUENOS_AIRES), [datetime.date(2027, 2, 6)])  # the annular one of February

    def test_a_lunar_eclipse_counts_with_the_moon_up_and_enough_umbra_and_gives_the_night_it_is_in(self):
        june, december = self.nights(2029)
        self.assertEqual([moment.strftime("%Y-%m-%d") for moment in (june[0], june[1], december[0])], ["2029-06-25", "2029-06-26", "2029-12-20"])
        self.assertLess(abs((june[0] - datetime.datetime(2029, 6, 25, 19, 49)).total_seconds()), 300)  # the sunset in Madrid, in UTC
        self.assertLess(abs((june[1] - datetime.datetime(2029, 6, 26, 4, 46)).total_seconds()), 300)  # and the next sunrise
        self.assertEqual(self.nights(2028), ())  # January: a bite of 0.06; July: below the horizon in Madrid; December: rising
        self.assertEqual(self.nights(2034), ())  # the umbra of 0.01
        self.assertTrue(astronomy.moon_is_up(*MADRID, [jde for kind, jde, _ in astronomy._eclipses_of(2029) if kind == "lunar"][0]))

    def test_the_minimums_are_the_ones_agreed(self):
        self.assertEqual((astronomy.SOLAR_MIN_MAGNITUDE, astronomy.LUNAR_MIN_UMBRAL), (0.25, 0.1))

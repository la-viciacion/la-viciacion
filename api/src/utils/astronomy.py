"""The sky, worked out locally: full moons, eclipses, solstices and equinoxes. No API, no key, no network.

The formulas are the ones of Jean Meeus, *Astronomical Algorithms* (2nd ed.): chapter 27 (equinoxes and
solstices), 49 (phases of the Moon) and 54 (eclipses). They are accurate to a couple of minutes over the years
that matter here, far more than a game session needs: the achievements only ask on which *day* something
happens. Which eclipses there are on the Earth comes from those formulas; whether one can be seen from a
given city (and how much of the Sun is covered there) is worked out with the positions of the Sun and the Moon of
the `ephem` library, which carries its own tables (nothing is downloaded).

Every instant is turned into the server's local time (`TZ`, Europe/Madrid in a deployment) with the C library,
the way the rest of the app reads the clock, so a "day" here is the same day as a session's date.
"""
import datetime
import functools
import math

import ephem

# TT - UT in seconds: 69 s in the 2020s, 72 s by 2040. A minute is enough for a day, so one value serves.
DELTA_T = 70.0
UNIX_EPOCH_JD = 2440587.5
# Mean length of a lunation, used to walk from a date to the number of the phase (k) near it.
SYNODIC_MONTH = 29.530588861
# The first new moon of the year 2000 is k = 0 (6 January 2000).
YEAR_2000_JD = 2451545.0


def _local(jde: float) -> datetime.datetime:
    """A moment given in Julian Ephemeris Days, as a naive datetime in the server's local time."""
    seconds = (jde - UNIX_EPOCH_JD) * 86400.0 - DELTA_T
    return datetime.datetime.fromtimestamp(seconds)


def _rad(degrees: float) -> float:
    return math.radians(degrees % 360.0)


def _sin(degrees: float) -> float:
    return math.sin(_rad(degrees))


def _cos(degrees: float) -> float:
    return math.cos(_rad(degrees))


def _k_range(year: int) -> range:
    """The numbers (k) of the new moons whose lunation overlaps the year, a little wider on both sides."""
    first = (datetime.date(year, 1, 1).toordinal() - datetime.date(2000, 1, 6).toordinal()) / SYNODIC_MONTH
    last = (datetime.date(year, 12, 31).toordinal() - datetime.date(2000, 1, 6).toordinal()) / SYNODIC_MONTH
    return range(math.floor(first) - 1, math.ceil(last) + 2)


class _Phase:
    """The arguments (Meeus 49.4-49.8) of the new moon (k integer) or full moon (k + 1/2) number k."""

    def __init__(self, k: float):
        self.k = k
        t = self.t = k / 1236.85
        self.e = 1 - 0.002516 * t - 0.0000074 * t * t
        self.mean = (
            2451550.09766 + SYNODIC_MONTH * k + 0.00015437 * t**2 - 0.000000150 * t**3 + 0.00000000073 * t**4
        )
        self.m = 2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3
        self.mp = 201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4
        self.f = 160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3 + 0.000000011 * t**4
        self.omega = 124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3

    def planetary(self) -> float:
        """The small correction of the planets (Meeus table 49.A), under a minute."""
        k, t = self.k, self.t
        terms = (
            (299.77 + 0.107408 * k - 0.009173 * t * t, 0.000325),
            (251.88 + 0.016321 * k, 0.000165),
            (251.83 + 26.651886 * k, 0.000164),
            (349.42 + 36.412478 * k, 0.000126),
            (84.66 + 18.206239 * k, 0.000110),
            (141.74 + 53.303771 * k, 0.000062),
            (207.14 + 2.453732 * k, 0.000060),
            (154.84 + 7.306860 * k, 0.000056),
            (34.52 + 27.261239 * k, 0.000047),
            (207.19 + 0.121824 * k, 0.000042),
            (291.34 + 1.844379 * k, 0.000040),
            (161.72 + 24.198154 * k, 0.000037),
            (239.56 + 25.513099 * k, 0.000035),
            (331.55 + 3.592518 * k, 0.000023),
        )
        return sum(amplitude * _sin(angle) for angle, amplitude in terms)

    def jde(self, full: bool) -> float:
        """The instant of the phase, in Julian Ephemeris Days."""
        e, m, mp, f, omega = self.e, self.m, self.mp, self.f, self.omega
        # the first terms are the only ones that differ between a new moon and a full moon
        main, sun, twice, nodes, difference, sum_ = (
            (-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515)
            if full
            else (-0.40720, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514)
        )
        c = (
            main * _sin(mp)
            + sun * e * _sin(m)
            + twice * _sin(2 * mp)
            + nodes * _sin(2 * f)
            + difference * e * _sin(mp - m)
            + sum_ * e * _sin(mp + m)
        )
        c += (
            0.00209 * e * e * _sin(2 * m)
            - 0.00111 * _sin(mp - 2 * f)
            - 0.00057 * _sin(mp + 2 * f)
            + 0.00056 * e * _sin(2 * mp + m)
            - 0.00042 * _sin(3 * mp)
            + 0.00042 * e * _sin(m + 2 * f)
            + 0.00038 * e * _sin(m - 2 * f)
            - 0.00024 * e * _sin(2 * mp - m)
            - 0.00017 * _sin(omega)
            - 0.00007 * _sin(mp + 2 * m)
            + 0.00004 * _sin(2 * mp - 2 * f)
            + 0.00004 * _sin(3 * m)
            + 0.00003 * _sin(mp + m - 2 * f)
            + 0.00003 * _sin(2 * mp + 2 * f)
            - 0.00003 * _sin(mp + m + 2 * f)
            + 0.00003 * _sin(mp - m + 2 * f)
            - 0.00002 * _sin(mp - m - 2 * f)
            - 0.00002 * _sin(3 * mp + m)
            + 0.00002 * _sin(4 * mp)
        )
        return self.mean + c + self.planetary()

    def eclipse(self, full: bool) -> tuple[float, float, float] | None:
        """(greatest eclipse in JDE, gamma, u) if the Moon is near enough to a node for an eclipse, else None
        (Meeus chapter 54). Gamma is how far from the middle of the Earth's shadow the Moon's axis passes."""
        if abs(_sin(self.f)) > 0.36:
            return None
        e, m, mp, omega = self.e, self.m, self.mp, self.omega
        f1 = self.f - 0.02665 * _sin(omega)
        a1 = 299.77 + 0.107408 * self.k - 0.009173 * self.t**2
        p = (
            0.2070 * e * _sin(m) + 0.0024 * e * _sin(2 * m) - 0.0392 * _sin(mp) + 0.0116 * _sin(2 * mp)
            - 0.0073 * e * _sin(mp + m) + 0.0067 * e * _sin(mp - m) + 0.0118 * _sin(2 * f1)
        )
        q = (
            5.2207 - 0.0048 * e * _cos(m) + 0.0020 * e * _cos(2 * m) - 0.3299 * _cos(mp)
            - 0.0060 * e * _cos(mp + m) + 0.0041 * e * _cos(mp - m)
        )
        w = abs(_cos(f1))
        gamma = (p * _cos(f1) + q * _sin(f1)) * (1 - 0.0048 * w)
        u = 0.0059 + 0.0046 * e * _cos(m) - 0.0182 * _cos(mp) + 0.0004 * _cos(2 * mp) - 0.0005 * _cos(m + mp)
        greatest = (
            self.mean
            + (-0.4065 if full else -0.4075) * _sin(mp)
            + (0.1727 if full else 0.1721) * e * _sin(m)
            + 0.0161 * _sin(2 * mp)
            - 0.0097 * _sin(2 * f1)
            + 0.0073 * e * _sin(mp - m)
            - 0.0050 * e * _sin(mp + m)
            - 0.0023 * _sin(mp - 2 * f1)
            + 0.0021 * e * _sin(2 * m)
            + 0.0012 * _sin(mp + 2 * f1)
            + 0.0006 * e * _sin(2 * mp + m)
            - 0.0004 * _sin(3 * mp)
            - 0.0003 * e * _sin(m + 2 * f1)
            + 0.0003 * _sin(a1)
            - 0.0002 * e * _sin(m - 2 * f1)
            - 0.0002 * e * _sin(2 * mp - m)
            - 0.0002 * _sin(omega)
        )
        return greatest, gamma, u


@functools.lru_cache(maxsize=None)
def full_moons(year: int) -> tuple[datetime.datetime, ...]:
    """The full moons that fall in the year, in local time."""
    moments = (_local(_Phase(k + 0.5).jde(full=True)) for k in _k_range(year))
    return tuple(moment for moment in moments if moment.year == year)


@functools.lru_cache(maxsize=None)
def _eclipses_of(year: int) -> tuple[tuple[str, float, float], ...]:
    """The eclipses of the year as (kind, greatest eclipse in Julian Ephemeris Days, umbral magnitude: of a lunar one,
    0 for a solar one), oldest first. The kind is "solar" (partial, annular, total or hybrid) or "lunar": only the
    ones where the Moon enters the umbra, partial or total. A penumbral one cannot be told with the naked eye."""
    found = []
    for k in _k_range(year):
        new = _Phase(k).eclipse(full=False)
        if new is not None and abs(new[1]) < 1.5433 + new[2]:
            found.append(("solar", new[0], 0.0))
        full = _Phase(k + 0.5).eclipse(full=True)
        umbral = 0.0 if full is None else (1.0128 - full[2] - abs(full[1])) / 0.5450
        if umbral > 0:
            found.append(("lunar", full[0], umbral))
    return tuple(sorted((item for item in found if _local(item[1]).year == year), key=lambda item: item[1]))


def eclipses(year: int) -> tuple[tuple[str, datetime.datetime], ...]:
    """The eclipses of the year anywhere on Earth as (kind, moment of the greatest eclipse in local time)."""
    return tuple((kind, _local(jde)) for kind, jde, _ in _eclipses_of(year))


# (A, B, C) of Meeus table 27.C: the periodic terms that bring a mean equinox or solstice to the true one.
_PERIODIC = (
    (485, 324.96, 1934.136), (203, 337.23, 32964.467), (199, 342.08, 20.186), (182, 27.85, 445267.112),
    (156, 73.14, 45036.886), (136, 171.52, 22518.443), (77, 222.54, 65928.934), (74, 296.72, 3034.906),
    (70, 243.58, 9037.513), (58, 119.81, 33718.147), (52, 297.17, 150.678), (50, 21.02, 2281.226),
    (45, 247.54, 29929.562), (44, 325.15, 31555.956), (29, 60.93, 4443.417), (18, 155.12, 67555.328),
    (17, 288.79, 4562.452), (16, 198.04, 62894.029), (14, 199.76, 31436.921), (12, 95.39, 14577.848),
    (12, 287.11, 31931.756), (12, 320.81, 34777.259), (9, 227.73, 1222.114), (8, 15.45, 16859.074),
)
# The polynomials of Meeus table 27.B (years 1000 to 3000), in Y = (year - 2000) / 1000.
_MEAN_EVENTS = {
    "SPRING_EQUINOX": (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
    "SUMMER_SOLSTICE": (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
    "AUTUMN_EQUINOX": (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
    "WINTER_SOLSTICE": (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032),
}


@functools.lru_cache(maxsize=None)
def sun_events(year: int) -> dict[str, datetime.datetime]:
    """The two equinoxes and two solstices of the year, in local time, by the name of each of them."""
    y = (year - 2000) / 1000.0
    found = {}
    for name, (c0, c1, c2, c3, c4) in _MEAN_EVENTS.items():
        mean = c0 + c1 * y + c2 * y**2 + c3 * y**3 + c4 * y**4
        t = (mean - YEAR_2000_JD) / 36525.0
        w = 35999.373 * t - 2.47
        correction = 1 + 0.0334 * _cos(w) + 0.0007 * _cos(2 * w)
        s = sum(a * _cos(b + c * t) for a, b, c in _PERIODIC)
        found[name] = _local(mean + 0.00001 * s / correction)
    return found


def moon_days(year: int) -> frozenset[datetime.date]:
    """The days of the year (local) on which there is a full moon."""
    return frozenset(moment.date() for moment in full_moons(year))


# What an eclipse has to be to count for a player: seen from their city, a solar one covering at least this fraction
# of the Sun's diameter, a lunar one entering the umbra at least this much (the Moon above the horizon at its greatest)
SOLAR_MIN_MAGNITUDE = 0.25
LUNAR_MIN_UMBRAL = 0.1
# The Julian Date of the zero of `ephem`'s dates (31 December 1899, 12:00)
_EPHEM_ZERO = 2415020.0
# How far from the greatest eclipse the sun is looked at, and how often: a solar eclipse lasts about three hours at
# most at one place
_SCAN_MINUTES = 210
_SCAN_STEP_MINUTES = 2


def _observer(latitude: float, longitude: float) -> ephem.Observer:
    observer = ephem.Observer()
    observer.lat, observer.lon = str(latitude), str(longitude)
    observer.elevation = 0
    observer.pressure = 0  # no refraction: the horizon is the geometric one, plenty for a day
    return observer


def _ephem_date(jde: float) -> ephem.Date:
    return ephem.Date(jde - DELTA_T / 86400.0 - _EPHEM_ZERO)


def solar_eclipse_at(latitude: float, longitude: float, jde: float) -> tuple[float, float]:
    """(the greatest magnitude, when it is, in JDE) of a solar eclipse as seen from a place, looking around the moment
    of the greatest eclipse of the Earth. The magnitude is the fraction of the Sun's diameter covered, with the Sun
    above the horizon: 0 if nothing is seen from there."""
    observer = _observer(latitude, longitude)
    best = (0.0, jde)
    for minutes in range(-_SCAN_MINUTES, _SCAN_MINUTES + 1, _SCAN_STEP_MINUTES):
        moment = jde + minutes / 1440.0
        observer.date = _ephem_date(moment)
        sun, moon = ephem.Sun(observer), ephem.Moon(observer)
        if sun.alt <= 0:
            continue
        separation = float(ephem.separation((sun.ra, sun.dec), (moon.ra, moon.dec)))
        magnitude = (float(sun.radius) + float(moon.radius) - separation) / (2 * float(sun.radius))
        if magnitude > best[0]:
            best = (magnitude, moment)
    return best


def moon_is_up(latitude: float, longitude: float, jde: float) -> bool:
    observer = _observer(latitude, longitude)
    observer.date = _ephem_date(jde)
    return ephem.Moon(observer).alt > 0


def _sunset_and_sunrise(latitude: float, longitude: float, jde: float) -> tuple[float, float] | None:
    """(the sunset before `jde`, the sunrise after it), both in JDE, or None if the Sun does not set there that day."""
    observer = _observer(latitude, longitude)
    observer.horizon = "-0:34"  # the usual one: the refraction of the horizon, with the pressure at 0 of `_observer`
    observer.date = _ephem_date(jde)
    try:
        setting = observer.previous_setting(ephem.Sun())
        rising = observer.next_rising(ephem.Sun())
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return None
    return tuple(float(moment) + _EPHEM_ZERO + DELTA_T / 86400.0 for moment in (setting, rising))


@functools.lru_cache(maxsize=None)
def _solar_eclipse_days_at(year: int, latitude: float, longitude: float) -> frozenset[datetime.date]:
    days = set()
    for kind, jde, _ in _eclipses_of(year):
        if kind == "solar":
            magnitude, when = solar_eclipse_at(latitude, longitude, jde)
            if magnitude >= SOLAR_MIN_MAGNITUDE:
                days.add(_local(when).date())
    return frozenset(days)


def solar_eclipse_days_at(year: int, latitude: float, longitude: float) -> frozenset[datetime.date]:
    """The days of the year (local) of the solar eclipses that count from a place: seen from there with at least
    `SOLAR_MIN_MAGNITUDE`. The place is taken to two decimals, about a kilometre."""
    return _solar_eclipse_days_at(year, round(latitude, 2), round(longitude, 2))


@functools.lru_cache(maxsize=None)
def _lunar_eclipse_nights_at(year: int, latitude: float, longitude: float) -> tuple[tuple[datetime.datetime, datetime.datetime], ...]:
    nights = []
    for kind, jde, umbral in _eclipses_of(year):
        if kind != "lunar" or umbral < LUNAR_MIN_UMBRAL or not moon_is_up(latitude, longitude, jde):
            continue
        night = _sunset_and_sunrise(latitude, longitude, jde)
        if night is not None:
            nights.append((_local(night[0]), _local(night[1])))
    return tuple(nights)


def lunar_eclipse_nights_at(year: int, latitude: float, longitude: float) -> tuple[tuple[datetime.datetime, datetime.datetime], ...]:
    """The nights of the year, as (sunset, next sunrise) in local time, in which a lunar eclipse counts from a place:
    the Moon is up at its greatest and enters the umbra by at least `LUNAR_MIN_UMBRAL`. Playing in one of them means
    starting after that sunset."""
    return _lunar_eclipse_nights_at(year, round(latitude, 2), round(longitude, 2))


def sun_event_days(year: int) -> dict[str, datetime.date]:
    """Equinox and solstice name -> its day (local)."""
    return {name: moment.date() for name, moment in sun_events(year).items()}

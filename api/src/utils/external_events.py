"""The days and the games that the achievements about the world outside the app are about.

Pure rules, with no database: which days of a year an achievement is about (a festivity, a birthday, a full moon, an
eclipse, a solstice...) and which games it asks for (a Star Wars one on the 4th of May). The checks that apply them to
the sessions of a player are in crud/achievements.py; the sky is in astronomy.py.
"""
import calendar
import datetime
import re

from . import astronomy

# A game is a Star Wars one by its name, or by RAWG's tag. The titles that do not say "Star Wars" are listed by hand.
STAR_WARS = re.compile(
    r"star\s*wars|\bjedi\b|\bsith\b|\bskywalker\b|\bmandalorian\b|old republic|tie fighter|\bx-?wing\b|\bbattlefront\b",
    re.IGNORECASE,
)
MARIO = re.compile(r"\bmario\b", re.IGNORECASE)
HORROR = re.compile(r"horror", re.IGNORECASE)

# How old a game has to be, in years, for "Arqueólogo"
ARCHAEOLOGIST_YEARS = 25


def is_star_wars(name: str | None, tags: str | None) -> bool:
    return bool(STAR_WARS.search(name or "") or re.search(r"star\s*wars", tags or "", re.IGNORECASE))


def is_mario(name: str | None, tags: str | None) -> bool:
    return bool(MARIO.search(name or ""))


def is_horror(name: str | None, tags: str | None) -> bool:
    """RAWG has no Horror genre, only tags such as Horror, Survival Horror or Psychological Horror."""
    return bool(HORROR.search(tags or ""))


def birthday(born: datetime.date, year: int) -> datetime.date:
    """The day of the year a person born on `born` celebrates: someone born on 29 February celebrates on the 28th
    in the years that have no 29th."""
    if born.month == 2 and born.day == 29 and not calendar.isleap(year):
        return datetime.date(year, 2, 28)
    return datetime.date(year, born.month, born.day)


def years_before(day: datetime.date, years: int) -> datetime.date:
    """The same day `years` years earlier (the 28th of February, for the 29th)."""
    year = day.year - years
    if day.month == 2 and day.day == 29 and not calendar.isleap(year):
        return datetime.date(year, 2, 28)
    return day.replace(year=year)


def is_archaeological(release: datetime.date | None, played: datetime.date) -> bool:
    """Was the game `ARCHAEOLOGIST_YEARS` years old (or more) on the day it was played?"""
    return release is not None and release <= years_before(played, ARCHAEOLOGIST_YEARS)


def _one_day(month: int, day: int):
    return lambda year, born: frozenset({datetime.date(year, month, day)})


def _leap_day(year: int, born) -> frozenset:
    return frozenset({datetime.date(year, 2, 29)}) if calendar.isleap(year) else frozenset()


def _birthday(year: int, born) -> frozenset:
    return frozenset() if born is None else frozenset({birthday(born, year)})


def _sun_event(name: str):
    return lambda year, born: frozenset({astronomy.sun_event_days(year)[name]})


# achievement key -> the days of a year it is about, given the player's birth date (None if they have not set it)
DAYS = {
    "STAR_WARS_DAY_LIFETIME": _one_day(5, 4),
    "MARIO_DAY_LIFETIME": _one_day(3, 10),
    "LEAP_DAY_LIFETIME": _leap_day,
    "BIRTHDAY_LIFETIME": _birthday,
    "FULL_MOON_LIFETIME": lambda year, born: astronomy.moon_days(year),
    "LUNAR_ECLIPSE_LIFETIME": lambda year, born: astronomy.eclipse_days(year, "lunar"),
    "SOLAR_ECLIPSE_LIFETIME": lambda year, born: astronomy.eclipse_days(year, "solar"),
    "SPRING_EQUINOX_LIFETIME": _sun_event("SPRING_EQUINOX"),
    "SUMMER_SOLSTICE_LIFETIME": _sun_event("SUMMER_SOLSTICE"),
    "AUTUMN_EQUINOX_LIFETIME": _sun_event("AUTUMN_EQUINOX"),
    "WINTER_SOLSTICE_LIFETIME": _sun_event("WINTER_SOLSTICE"),
}

# the ones that also ask for a kind of game: (name, tags) -> bool
GAME_RULES = {
    "STAR_WARS_DAY_LIFETIME": is_star_wars,
    "MARIO_DAY_LIFETIME": is_mario,
}


def days_of(key: str, years, born: datetime.date | None) -> frozenset[datetime.date]:
    """Every day of `years` that the achievement `key` is about."""
    return frozenset(day for year in years for day in DAYS[key](year, born))

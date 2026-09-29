"""The one place that knows what a season is.

A season is a calendar year. It is never stored on its own: the database
derives it from the date of each row (users_games.season from started_date,
game_timers.season from start_time, users_achievements.season from date) so it
cannot drift from that date. The running season is the year of today's date on
the server (see the TZ variable of the deployment).
"""
import datetime


def current() -> int:
    """The running season."""
    return datetime.date.today().year


def or_current(season: int | None) -> int:
    """`season` if given, else the running one (for optional query params)."""
    return current() if season is None else season


def of(day: datetime.date | datetime.datetime) -> int:
    """Season a date belongs to."""
    return day.year

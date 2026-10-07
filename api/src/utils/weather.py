"""The weather of a past day at a place, from Open-Meteo (free, no key).

Only what the achievements need: the WMO weather code of each hour (95-99 is a thunderstorm, 45 and 48 fog). A day
that is over never changes, so it is asked for once and kept (`weather_days`); today is asked for again every time.
The forecast service has the last three months and the archive service the rest (a few days late), so a request
goes to one or the other by how old its days are.

Open-Meteo is outside our control, so every failure is a `WeatherUnavailable` that the caller treats as "cannot
tell now": it never blocks a timer, and after one failure no request is made for a few minutes.
"""
import datetime
import os
import time

import requests
from sqlalchemy.orm import Session

from ..database import models
from .logger import LogManager

logger = LogManager().get_logger()

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# The forecast service keeps 92 past days: use it for what is newer than this, and the archive for what is older
FORECAST_DAYS = 80
# At most this many days in a request
CHUNK_DAYS = 60
TIMEOUT = 8
RETRY_AFTER_SECONDS = 300

THUNDERSTORM = frozenset({95, 96, 99})
FOG = frozenset({45, 48})

_down_until = 0.0


class WeatherUnavailable(Exception):
    """Open-Meteo did not give the weather asked for."""


def place_key(latitude: float, longitude: float) -> str:
    """The place as the cache knows it: rounded to two decimals, about a kilometre."""
    return f"{float(latitude):.2f},{float(longitude):.2f}"


def time_zone() -> str:
    """The time zone sessions are recorded in (the server's `TZ`), so that an hour of a session is the same hour here."""
    return os.environ.get("TZ") or "Europe/Madrid"


def parse(payload: dict) -> dict[datetime.date, list[int | None]]:
    """{day: the 24 codes of its hours (None where Open-Meteo has none)} out of an answer of the service."""
    hourly = payload.get("hourly") or {}
    days: dict[datetime.date, list[int | None]] = {}
    for stamp, code in zip(hourly.get("time") or [], hourly.get("weather_code") or []):
        slots = days.setdefault(datetime.date.fromisoformat(stamp[:10]), [None] * 24)
        slots[int(stamp[11:13])] = None if code is None else int(code)
    return days


def _pack(codes: list[int | None]) -> str:
    return ",".join("" if code is None else str(code) for code in codes)


def _unpack(text: str) -> list[int | None]:
    return [int(part) if part else None for part in text.split(",")]


def _request(url: str, latitude: float, longitude: float, first: datetime.date, last: datetime.date) -> dict:
    global _down_until
    if time.monotonic() < _down_until:
        raise WeatherUnavailable("Open-Meteo failed a moment ago")
    try:
        response = requests.get(
            url,
            params={
                "latitude": f"{float(latitude):.2f}", "longitude": f"{float(longitude):.2f}",
                "start_date": first.isoformat(), "end_date": last.isoformat(),
                "hourly": "weather_code", "timezone": time_zone(),
            },
            timeout=TIMEOUT,
        )
        if not response.ok:
            raise WeatherUnavailable(f"HTTP {response.status_code}")
        return parse(response.json())
    except (requests.RequestException, ValueError, KeyError) as e:
        _down_until = time.monotonic() + RETRY_AFTER_SECONDS
        logger.warning("Open-Meteo failed: " + str(e))
        raise WeatherUnavailable(str(e))
    except WeatherUnavailable:
        _down_until = time.monotonic() + RETRY_AFTER_SECONDS
        raise


def chunks(days: list[datetime.date], today: datetime.date) -> list[tuple[str, datetime.date, datetime.date]]:
    """The requests that bring `days`: (service, first day, last day), the old days to the archive and the recent
    ones to the forecast service, none of them longer than CHUNK_DAYS."""
    boundary = today - datetime.timedelta(days=FORECAST_DAYS)
    found: list[tuple[str, datetime.date, datetime.date]] = []
    for url, group in (
        (ARCHIVE_URL, [day for day in days if day < boundary]),
        (FORECAST_URL, [day for day in days if day >= boundary]),
    ):
        start = previous = None
        for day in sorted(group):
            if start is None:
                start = previous = day
            elif (day - start).days >= CHUNK_DAYS:
                found.append((url, start, previous))
                start = previous = day
            else:
                previous = day
        if start is not None:
            found.append((url, start, previous))
    return found


def codes_for_days(
    db: Session, latitude: float, longitude: float, days, today: datetime.date | None = None
) -> dict[datetime.date, list[int | None]]:
    """{day: its 24 hourly weather codes} for each of `days` at the place, from the cache or Open-Meteo. A day that
    is over and complete is kept for good. Raises WeatherUnavailable if a day cannot be had."""
    today = today or datetime.date.today()
    key = place_key(latitude, longitude)
    wanted = set(days)
    if not wanted:
        return {}
    have = {
        row.day: _unpack(row.codes)
        for row in db.query(models.WeatherDay).filter(models.WeatherDay.place == key, models.WeatherDay.day.in_(wanted))
    }
    missing = sorted(wanted - set(have))
    for url, first, last in chunks(missing, today):
        for day, codes in _request(url, latitude, longitude, first, last).items():
            if day not in wanted:
                continue
            have[day] = codes
            if day < today and None not in codes:
                db.merge(models.WeatherDay(place=key, day=day, codes=_pack(codes)))
        db.commit()
    return have


def at(codes: dict[datetime.date, list[int | None]], moment: datetime.datetime, wanted) -> bool:
    """Was the weather of the hour of `moment` one of the `wanted` codes? (False for a day it knows nothing about.)"""
    day = codes.get(moment.date())
    return day is not None and day[moment.hour] in wanted

"""The clock of the tests: a fixed time of day that keeps ticking, so no test depends on when it runs.

The application reads the real clock (`datetime.date.today()`, `datetime.datetime.now()`), and the tests build their
data relative to it ("a session 5 hours ago"). Run at 03:00, "5 hours ago" is yesterday and the same fixture gives a
different ranking than at noon. Instead of dodging each fixture, every test run starts at `PIN` (a Wednesday at
noon) and the clock goes on from there, so "hours ago" never crosses midnight and the date, and with it the
running season, is the same on every machine and every day.

`install()` runs by itself when the first test starts (see `tests/__init__.py`), not when `tests` is imported: the
application's modules and its pydantic and SQLAlchemy types are built before that, with the real `datetime` classes.
Anything read at import time therefore escapes the pinned clock, and `tests/test_clock.py` fails a test module that
does it: use `PIN`, `YEAR` or `today()` inside the test instead.

What is pinned: the `datetime` module as the repository's own code (`src`, `tests`) sees it, and the MariaDB test connections
(`CURRENT_TIMESTAMP` defaults). Libraries keep the real clock, so a token the tests mint for PyJWT must use `real_now()`.

To try another day of 2026 (a Sunday, the last day of a month...) set `TEST_NOW=2026-12-31T12:00:00`. Keep the year and a daytime
hour: several fixtures write 2026 by hand, and "5 hours ago" only stays in the same day after 05:00.
"""
import datetime
import os
import sys
import types
import unittest
from datetime import timedelta

_stdlib = datetime  # this module's own `datetime` is swapped too, so keep the real one
_real_date = datetime.date
_real_datetime = datetime.datetime

PIN = _real_datetime.fromisoformat(os.environ.get("TEST_NOW") or "2026-06-17T12:00:00")
YEAR = PIN.year

_offset: timedelta | None = None


def now() -> datetime.datetime:
    """The pinned moment, to the second, as it was when the test run started plus the time that has passed."""
    return _Datetime.now().replace(microsecond=0) if _offset is not None else _real_datetime.now().replace(microsecond=0)


def today() -> datetime.date:
    return now().date()


def real_now() -> datetime.datetime:
    """The real UTC moment, for what a library outside this repository checks against its own clock (a JWT's expiry)."""
    return _real_datetime.now(datetime.timezone.utc)


def ago(**delta) -> datetime.datetime:
    """A moment in the past, to the second."""
    return now() - timedelta(**delta)


class _Meta(type):
    """`isinstance(real_value, datetime.date)` keeps working: values are always real `date`/`datetime` objects."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)


class _Date(_real_date, metaclass=_Meta):
    _real = _real_date

    def __new__(cls, *args, **kwargs):
        return _real_date(*args, **kwargs)

    @classmethod
    def today(cls):
        return _Datetime.now().date()


class _Datetime(_real_datetime, metaclass=_Meta):
    _real = _real_datetime

    def __new__(cls, *args, **kwargs):
        return _real_datetime(*args, **kwargs)

    @classmethod
    def now(cls, tz=None):
        return _real_datetime.now(tz) + _offset

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        return _real_datetime.now(datetime.timezone.utc).replace(tzinfo=None) + _offset


def install() -> None:
    """Pin the clock for the rest of the process. Idempotent.

    Only the code of this repository sees it: every `src` and `tests` module that did `import datetime` gets a copy
    of the module whose `date` and `datetime` are the pinned classes. Third-party code (PyJWT checking a token's
    expiry, pymysql, pydantic) keeps the real ones, so a library imported late never meets a class it cannot
    subclass, and `src/auth.py` (`from datetime import datetime`) stays on the real clock together with PyJWT.
    """
    global _offset
    if _offset is not None:
        return
    _offset = PIN - _real_datetime.now()
    pinned = types.ModuleType("datetime")
    pinned.__dict__.update({name: getattr(_stdlib, name) for name in dir(_stdlib) if not name.startswith("__")})
    pinned.date, pinned.datetime = _Date, _Datetime
    for name, module in list(sys.modules.items()):
        if module is not None and (name in ("src", "tests") or name.startswith(("src.", "tests."))) and getattr(module, "datetime", None) is _stdlib:
            module.datetime = pinned


def install_on_first_run() -> None:
    """Pin the clock when the suite starts running: by then every test module is imported (see the module docstring)."""
    original = unittest.TestSuite.run

    def run(self, *args, **kwargs):
        install()
        return original(self, *args, **kwargs)

    unittest.TestSuite.run = run
